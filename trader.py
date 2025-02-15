import json
import os
import logging
import asyncio
import argparse
import time

from pathlib import Path
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters
)

# Импортируйте ваш OpenAI SDK, как у вас настроено
import openai
from openai import OpenAI

# Файлы
USERS_FILE = "users.json"
INFO_FILE = "info.json"

# ID вашего ассистента в OpenAI
ASSISTANT_ID = "asst_VxE0V10Gi7Q3EXRIFvUSbqTp"

# Настраиваем логирование

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    encoding='utf-8'
)


# ------------------------------------------------------------------------------
# Загрузка и сохранение данных
# ------------------------------------------------------------------------------
def load_data(file_path):
    if not Path(file_path).exists():
        # Создаём файл и инициализируем пустой структурой
        if file_path == INFO_FILE:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump([], f, ensure_ascii=False, indent=4)
        else:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump({}, f, ensure_ascii=False, indent=4)
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_data(file_path, data):
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


users = load_data(USERS_FILE)
info = load_data(INFO_FILE)


# ------------------------------------------------------------------------------
# Функции работы с пользователями и товарами
# ------------------------------------------------------------------------------
def get_user(user_id: str):
    return users.get(user_id)


def create_user(user_id: str, name: str):
    users[user_id] = {
        "name": name,
        "balance": 0,
        "thread_id": None
    }
    save_data(USERS_FILE, users)
    return users[user_id]


def update_balance(user_id: str, amount: int):
    users[user_id]["balance"] += amount
    save_data(USERS_FILE, users)


def add_info(user_id, user_name, description, details, cost):
    info.append({
        "id": len(info) + 1,
        "description": description,
        "details": details,
        "cost": cost,
        "seller_id": user_id,
        "seller_name": user_name
    })
    save_data(INFO_FILE, info)


def handle_show_items():
    return [
        {"id": item["id"], "description": item["description"], "cost": item["cost"]}
        for item in info
    ]


def handle_buy_item(user_id, item_id):
    item = next((x for x in info if x["id"] == item_id), None)
    if not item:
        return "Item not found."

    user = get_user(user_id)
    if user["balance"] < item["cost"]:
        return "Insufficient balance."

    update_balance(user_id, -item["cost"])
    return item["details"]


def handle_sell_item(user_id, description, details, cost):
    user = get_user(user_id)
    add_info(user_id, user["name"], description, details, cost)
    update_balance(user_id, cost)
    return f"Информация продана за {cost} кредитов. Ваш новый баланс: {users[user_id]['balance']} кредитов."


def handle_get_purchased_items():
    return [item["description"] for item in info]


# ------------------------------------------------------------------------------
# Функции взаимодействия с OpenAI Threads
# ------------------------------------------------------------------------------
def add_message_to_thread(client, thread_id, role, content, user_id=None):
    """Добавляет сообщение в указанный поток."""
    user_info = ""
    if user_id:
        user = get_user(user_id)
        user_info = f" ({user['name']}, баланс: {user['balance']} кредитов)"
    message_content = f"{content}{user_info}"
    logging.info(f"Adding message to thread {thread_id}: {role} - {message_content}")
    client.beta.threads.messages.create(
        thread_id=thread_id,
        role=role,
        content=message_content
    )


def submit_tool_outputs(client, thread_id, run_id, tool_outputs):
    """Отправляет результаты выполнения 'инструментов' (tool calls) в поток."""
    logging.info(f"Submitting tool outputs for run {run_id} in thread {thread_id}: {tool_outputs}")
    response = client.beta.threads.runs.submit_tool_outputs(
        thread_id=thread_id,
        run_id=run_id,
        tool_outputs=tool_outputs
    )
    return response


async def run_assistant(client, thread_id, assistant_id, user_id):
    """Запускает ассистента на указанном потоке и обрабатывает его ответы."""
    logging.info(f"Running assistant {assistant_id} on thread {thread_id}")
    run = client.beta.threads.runs.create(
        thread_id=thread_id,
        assistant_id=assistant_id
    )

    while True:
        # Вместо time.sleep используем asyncio.sleep для асинхронности
        await asyncio.sleep(3)
        run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
        logging.info(f"Run status: {run.status}")

        if run.status in ["queued", "in_progress"]:
            continue
        elif run.status == "requires_action":
            logging.warning(f"Run requires action: {run.required_action}")
            tool_calls = run.required_action.submit_tool_outputs.tool_calls
            tool_outputs = []
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)
                if function_name == "sell_item":
                    result = handle_sell_item(user_id, arguments["description"], arguments["details"],
                                              arguments["cost"])
                elif function_name == "buy_item":
                    result = handle_buy_item(user_id, arguments["item_id"])
                elif function_name == "show_items":
                    result = handle_show_items()
                elif function_name == "get_purchased_items":
                    result = handle_get_purchased_items()
                else:
                    result = "Unknown function call."

                tool_outputs.append({
                    "tool_call_id": tool_call.id,
                    "output": json.dumps(result, ensure_ascii=False)
                })
            submit_tool_outputs(client, thread_id, run.id, tool_outputs)

        elif run.status in ["cancelling", "cancelled", "failed", "incomplete", "expired"]:
            logging.error(f"Run ended with status: {run.status}")
            return []  # Возвращаем пустой список сообщений
        elif run.status == "completed":
            # Получаем все сообщения потока
            messages = client.beta.threads.messages.list(thread_id=thread_id).data
            logging.info(f"Received messages: {messages}")
            return messages
    return []


# ------------------------------------------------------------------------------
# Handlers для Телеграма
# ------------------------------------------------------------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /start."""
    chat_id = str(update.effective_chat.id)
    telegram_user = update.effective_user

    # Если пользователь не существует в хранилище - создаём
    user = get_user(chat_id)
    if not user:
        # Берём имя из Telegram (если пустое, подставьте что-то по умолчанию)
        name = telegram_user.first_name or "NoName"
        user = create_user(chat_id, name)
        await update.message.reply_text(
            f"Привет, {user['name']}! Я создал для вас нового пользователя."
        )
    else:
        await update.message.reply_text(
            f"С возвращением, {user['name']}!"
        )

    # Проверяем, есть ли у пользователя поток (thread_id)
    client = context.application.bot_data["openai_client"]  # См. ниже, как мы туда положим client
    if not user.get("thread_id"):
        # Создаём новый поток
        thread = client.beta.threads.create()
        user["thread_id"] = thread.id
        save_data(USERS_FILE, users)
        await update.message.reply_text("Создал новый поток (thread) для вашего пользователя.")
    else:
        # Пробуем получить существующий поток
        try:
            thread = client.beta.threads.retrieve(thread_id=user["thread_id"])
            await update.message.reply_text("Продолжаем общение в существующем потоке.")
        except Exception as e:
            logging.error(f"Не удалось получить существующий поток: {e}")
            # Создаём новый поток, если старый недоступен
            thread = client.beta.threads.create()
            user["thread_id"] = thread.id
            save_data(USERS_FILE, users)
            await update.message.reply_text("Создал новый поток, так как старый недоступен.")

    # Выводим баланс
    await update.message.reply_text(f"Ваш баланс: {user['balance']} кредитов.")


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка любого текстового сообщения (не команды)."""
    chat_id = str(update.effective_chat.id)
    user = get_user(chat_id)

    if not user:
        # Если почему-то пользователь ещё не создан, то перенаправим на /start
        await update.message.reply_text("Для начала введите /start")
        return

    client = context.application.bot_data["openai_client"]

    # Добавляем сообщение пользователя в поток
    add_message_to_thread(
        client=client,
        thread_id=user["thread_id"],
        role="user",
        content=update.message.text,
        user_id=chat_id
    )

    # Запускаем ассистента
    messages = await run_assistant(
        client=client,
        thread_id=user["thread_id"],
        assistant_id=ASSISTANT_ID,
        user_id=chat_id
    )

    # Ищем последнее сообщение ассистента и отправляем ответ
    assistant_text = None
    for msg in messages:
        if msg.role == "assistant":
            # В рамках Threads API контент ассистента может быть в msg.content[0].text.value
            # или иной структуре (зависит от версии), адаптируйте под свой случай
            # Предположим, что это msg.content[0].text.value
            if msg.content and isinstance(msg.content, list):
                assistant_text = msg.content[0].text.value
            else:
                assistant_text = str(msg.content)
            break

    if assistant_text:
        await update.message.reply_text(assistant_text)
    else:
        await update.message.reply_text("Не получил ответ от ассистента.")


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка неизвестных команд."""
    await update.message.reply_text("Извините, я не знаю такой команды.")


# ------------------------------------------------------------------------------
# Основная точка входа
# ------------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--api_key", required=True, help="OpenAI API Key")
    parser.add_argument("--telegram_token", required=True, help="Telegram Bot Token")
    args = parser.parse_args()

    # Инициализация клиента OpenAI
    openai_client = OpenAI(api_key=args.api_key)

    # Создаём приложение Telegram
    application = (
        ApplicationBuilder()
        .token(args.telegram_token)
        .build()
    )

    # В bot_data сложим наш openai_client, чтобы иметь доступ в хендлерах
    application.bot_data["openai_client"] = openai_client

    # Регистрируем хендлеры
    application.add_handler(CommandHandler("start", cmd_start))
    # Текстовые сообщения (не команды)
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text_message))

    # Хендлер для неизвестных команд
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    # Запускаем бота
    application.run_polling()


if __name__ == "__main__":
    main()
