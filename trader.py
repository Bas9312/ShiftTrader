import json
import os
import logging
import asyncio
import argparse
import re
from datetime import datetime
from pathlib import Path
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    CommandHandler,
    MessageHandler,
    filters,
    ConversationHandler
)
import random

# Импортируйте ваш OpenAI SDK, как у вас настроено
import openai
from openai import OpenAI

# Файлы
USERS_FILE = "users.json"
INFO_FILE = "info.json"
LOGS_DIR = "logs"
INFO_ABOUT_WORLD_FILE = "info_about_world.json"
PURCHASE_HISTORY_FILE = "purchase_history.json"

# ID вашего ассистента в OpenAI
ASSISTANT_ID = "asst_VxE0V10Gi7Q3EXRIFvUSbqTp"

# Состояния для ConversationHandler
WAITING_FOR_NAME = 1

# Создаем директорию для логов, если её нет
if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

# Настраиваем общее логирование
general_logger = logging.getLogger('general')
general_logger.setLevel(logging.DEBUG)
general_handler = logging.FileHandler(os.path.join(LOGS_DIR, 'general.log'), encoding='utf-8')
general_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
general_logger.addHandler(general_handler)

# Логирование операций
OPERATIONS_LOG = "operations.log"
def log_operation(text):
    with open(OPERATIONS_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {text}\n")

# Функция для получения логгера пользователя
def get_user_logger(user_id: str, user_name: str) -> logging.Logger:
    logger = logging.getLogger(f'user_{user_id}')
    if not logger.handlers:
        handler = logging.FileHandler(
            os.path.join(LOGS_DIR, f'user_{user_id}_{user_name}.log'),
            encoding='utf-8'
        )
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger

# ------------------------------------------------------------------------------
# Загрузка и сохранение данных
# ------------------------------------------------------------------------------
def load_data(file_path):
    if not Path(file_path).exists():
        # Создаём файл и инициализируем пустой структурой
        if file_path == INFO_FILE:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump({"1": [], "2": [], "3": [], "4": [], "5": [], "6": []}, f, ensure_ascii=False, indent=4)
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


# Новая структура info: категории -> массивы инфы
CATEGORY_NAMES = {
    "1": "О магических дисциплинах (от особого поставщика)",
    "2": "О магических дисциплинах",
    "3": "О конкретных волшебниках или их группах",
    "4": "О магических существах",
    "5": "О магических местах и артефактах",
    "6": "Прочие знания"
}

def get_categories_with_counts():
    """Вернуть список категорий и количество информации в каждой."""
    return [
        {"id": cat_id, "name": CATEGORY_NAMES.get(cat_id, cat_id), "count": len(info[cat_id])}
        for cat_id in info.keys()
    ]

def add_info(category_id, user_id, user_name, description, details, cost, cost_name="штукарики"):
    if category_id == 0:
        raise Exception("В категорию 0 нельзя продавать информацию! Особый поставщик только продает.")
    # id внутри категории
    new_id = 1
    if info[str(category_id)]:
        new_id = max(item["id"] for item in info[str(category_id)]) + 1
    info[str(category_id)].append({
        "id": new_id,
        "description": description,
        "details": details,
        "cost": cost,
        "cost_name": cost_name,
        "seller_id": user_id,
        "seller_name": user_name
    })
    save_data(INFO_FILE, info)
    return new_id


def handle_show_items(category_id):
    if str(category_id) not in info:
        return f"Категория с id {category_id} не найдена."
    return [
        {"id": item["id"], "description": item["description"], "cost": item["cost"], "cost_name": item.get("cost_name", "штукарики")}
        for item in info[str(category_id)]
    ]


def save_purchase_history(user_id, category_id, item):
    try:
        if os.path.exists(PURCHASE_HISTORY_FILE):
            with open(PURCHASE_HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        else:
            history = {}
        user_id_str = str(user_id)
        if user_id_str not in history:
            history[user_id_str] = []
        history[user_id_str].append({
            "category_id": category_id,
            "id": item["id"],
            "description": item["description"],
            "details": item["details"],
            "cost": item["cost"],
            "cost_name": item.get("cost_name", "штукарики")
        })
        with open(PURCHASE_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=4)
    except Exception as e:
        general_logger.error(f"Ошибка при сохранении purchase_history: {e}")

def get_user_purchase_history(user_id):
    try:
        if not os.path.exists(PURCHASE_HISTORY_FILE):
            return []
        with open(PURCHASE_HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
        return history.get(str(user_id), [])
    except Exception as e:
        return f"Ошибка при получении purchase_history: {e}"

def handle_buy_item(user_id, category_id, item_id):
    if str(category_id) not in info:
        return f"Категория с id {category_id} не найдена."
    item = next((x for x in info[str(category_id)] if x["id"] == item_id), None)
    if not item:
        return "В категории не найдена информация с заданным id"
    user = get_user(user_id)
    if user["balance"] < item["cost"]:
        return "Недостаточно кредитов на балансе"
    update_balance(user_id, -item["cost"])
    log_operation(f'{user["name"]} ({user_id}) купил информацию: {item["description"]} ({item["details"]}), за {item["cost"]} {item.get("cost_name", "штукарики")}.')
    save_purchase_history(user_id, category_id, item)
    return f"Информация успешно куплена за {item['cost']}, вот её описание {item['details']}"


def handle_sell_item(user_id, description, details, cost, category_id, cost_name="штукарики"):
    if str(category_id) not in info:
        return f"Категория с id {category_id} не найдена."
    if category_id == 1:
        return "В категорию 1 нельзя продавать информацию! Особый поставщик только продает."
    user = get_user(user_id)
    пояснения = []
    orig_cost = cost
    if cost > 3:
        cost = 3
        пояснения.append("(нельзя продать дороже 3 кредитов, цена скорректирована до 3)")
    if cost < 1:
        cost = 1
        пояснения.append("(нельзя продать дешевле 1 кредита, цена скорректирована до 1)")
    if len(details) < 200:
        return "ОШИБКА: Описание информации слишком короткое (меньше 200 символов). Пожалуйста, опишите информацию подробнее."
    new_id = add_info(category_id, user_id, user["name"], description, details, cost, cost_name)
    update_balance(user_id, cost)
    log_operation(f'{user["name"]} ({user_id}) продал информацию: {description} ({details}), за {cost} {cost_name} (категория {category_id}, id {new_id}).')
    пояснение = " ".join(пояснения)
    return f"Информация продана за {cost} {cost_name}. {пояснение} Ваш новый баланс: {users[user_id]['balance']} {cost_name}."


def handle_get_purchased_items(user_id):
    # Вернуть список купленных описаний и деталей по всем категориям
    purchased = []
    for cat_id, items in info.items():
        for item in items:
            if item.get("seller_id") == user_id:
                purchased.append({
                    "description": item["description"],
                    "details": item["details"]
                })
    return purchased

async def get_info_from_category(category_id, user_id, context):
    if str(category_id) not in info:
        return f"Категория {category_id} не найдена."
    category_name = CATEGORY_NAMES.get(str(category_id), f"Категория {category_id}")
    items = info[str(category_id)]
    if not items:
        return f"В категории '{category_name}' пока нет информации."
    items_json = []
    for idx, item in enumerate(items, 1):
        items_json.append({
            "id": idx,
            "description": item.get("description", "<без описания>"),
            "cost": item.get("cost", 0),
            "cost_name": item.get("cost_name", "штукарики")
        })

    return items_json



def get_random_info_about_world():
    try:
        with open(INFO_ABOUT_WORLD_FILE, "r", encoding="utf-8") as f:
            facts = json.load(f)
        if not isinstance(facts, list) or not facts:
            return "Нет фактов о мире."
        return random.choice(facts)
    except Exception as e:
        return f"Ошибка при получении факта о мире: {e}"
# ------------------------------------------------------------------------------
# Функции взаимодействия с OpenAI Threads
# ------------------------------------------------------------------------------
def add_message_to_thread(client, thread_id, role, content, user_id=None):
    """Добавляет сообщение в указанный поток."""
    user_info = ""
    if user_id:
        user = get_user(user_id)
        user_info = f" ({user['name']}, баланс: {user['balance']})"
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


async def run_assistant(client, thread_id, assistant_id, user_id, context):
    """Запускает ассистента на указанном потоке и обрабатывает его ответы."""
    logging.info(f"Running assistant {assistant_id} on thread {thread_id}")
    run = client.beta.threads.runs.create(
        thread_id       = thread_id,
        assistant_id    = assistant_id,
        truncation_strategy={
            "type": "last_messages",
            "last_messages": 8    # можно смело уменьшить до 4–6
        },
        max_completion_tokens = 1024    # опционально
    )

    iteration = 0
    while True:
        iteration += 1
        if iteration > 30:
            general_logger.error(f"Run for thread {thread_id} exceeded 30 iterations, cancelling.")
            try:
                client.beta.threads.runs.cancel(thread_id=thread_id, run_id=run.id)
            except Exception as e:
                general_logger.error(f"Error cancelling run: {e}")
            return [{"error": "❌ ОШИБКА: Не удалось получить ответ от ассистента. Попробуйте позже."}]
        await asyncio.sleep(3)
        run = client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
        general_logger.info(f"Iteration {iteration}: Run status: {run.status}")

        if run.status in ["queued", "in_progress"]:
            general_logger.info(f"Run still in progress (iteration {iteration}), waiting...")
            continue
        elif run.status == "requires_action":
            general_logger.warning(f"Run requires action: {run.required_action}")
            tool_calls = run.required_action.submit_tool_outputs.tool_calls
            general_logger.info(f"Processing {len(tool_calls)} tool calls")
            tool_outputs = []
            for tool_call in tool_calls:
                function_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)
                general_logger.info(f"Executing tool: {function_name} with args: {arguments}")
                
                if function_name == "sell_item":
                    result = handle_sell_item(
                        user_id,
                        arguments["description"],
                        arguments["details"],
                        arguments["cost"],
                        int(arguments["category_id"]),
                        arguments.get("cost_name", "штукарики")
                    )
                elif function_name == "buy_item":
                    result = handle_buy_item(
                        user_id,
                        int(arguments["category_id"]),
                        arguments["item_id"]
                    )
                elif function_name == "get_items_for_category":
                    result = handle_show_items(int(arguments["category_id"]))
                elif function_name == "get_purchased_items":
                    result = handle_get_purchased_items(user_id)
                elif function_name == "get_categories_with_counts":
                    result = get_categories_with_counts()
                elif function_name == "get_info_from_category":
                    result = await get_info_from_category(int(arguments["category_id"]), user_id, context)
                elif function_name == "get_random_info_about_world":
                    result = get_random_info_about_world()
                elif function_name == "get_user_purchase_history":
                    result = get_user_purchase_history(user_id)
                else:
                    result = "Unknown function call."

                general_logger.info(f"Tool {function_name} result: {result}")
                tool_outputs.append({
                    "tool_call_id": tool_call.id,
                    "output": json.dumps(result, ensure_ascii=False)
                })
            submit_tool_outputs(client, thread_id, run.id, tool_outputs)

        elif run.status in ["cancelling", "cancelled", "failed", "incomplete", "expired"]:
            general_logger.error(f"Run ended with status: {run.status}")
            if hasattr(run, 'last_error') and run.last_error:
                general_logger.error(f"Last error: {run.last_error}")
            return []  # Возвращаем пустой список сообщений
        elif run.status == "completed":
            general_logger.info(f"Run completed successfully after {iteration} iterations")
            general_logger.debug(f"Run costs {run.usage}")
            # Получаем все сообщения потока
            messages = client.beta.threads.messages.list(thread_id=thread_id).data
            general_logger.info(f"Retrieved {len(messages)} messages from thread")
            for i, msg in enumerate(messages):
                general_logger.info(f"Message {i+1}: role={msg.role}, content_type={type(msg.content)}")
            # Фильтруем все подряд идущие с конца сообщения ассистента до первого user
            assistant_msgs = []
            for msg in messages:
                if msg.role == "assistant":
                    assistant_msgs.append(msg)
                elif msg.role == "user":
                    break
            # Отправим их в обратном порядке (от старого к новому)
            assistant_msgs = list(reversed(assistant_msgs))
            return assistant_msgs
    return []


# ------------------------------------------------------------------------------
# Handlers для Телеграма
# ------------------------------------------------------------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка команды /start."""
    chat_id = str(update.effective_chat.id)
    user = get_user(chat_id)

    if not user:
        await update.message.reply_text(
            "Привет! Я бот для обмена информацией. Пожалуйста, введите ваше имя:"
        )
        return WAITING_FOR_NAME
    else:
        user_logger = get_user_logger(chat_id, user["name"])
        user_logger.info(f"Пользователь {user['name']} запустил бота")
        await update.message.reply_text(
            f"С возвращением, {user['name']}!",
            parse_mode='HTML'
        )

        # Проверяем, есть ли у пользователя поток (thread_id)
        client = context.application.bot_data["openai_client"]
        if not user.get("thread_id"):
            # Создаём новый поток
            thread = client.beta.threads.create()
            user["thread_id"] = thread.id
            save_data(USERS_FILE, users)
            user_logger.info("Создан новый поток (thread) для пользователя")
            await update.message.reply_text("Создал новый поток (thread) для вашего пользователя.", parse_mode='HTML')
        else:
            # Пробуем получить существующий поток
            try:
                thread = client.beta.threads.retrieve(thread_id=user["thread_id"])
                user_logger.info("Продолжение общения в существующем потоке")
                await update.message.reply_text("Продолжаем общение в существующем потоке.", parse_mode='HTML')
            except Exception as e:
                general_logger.error(f"Не удалось получить существующий поток: {e}")
                # Создаём новый поток, если старый недоступен
                thread = client.beta.threads.create()
                user["thread_id"] = thread.id
                save_data(USERS_FILE, users)
                user_logger.info("Создан новый поток из-за недоступности старого")
                await update.message.reply_text("Создал новый поток, так как старый недоступен.", parse_mode='HTML')

        # Выводим баланс
        await update.message.reply_text(f"Ваш баланс: {user['balance']} кредитов. Привет, я Меняла, у меня есть всякая информация, её можно купить. А можно продать свою. Просто начни разговор.", parse_mode='HTML')
        return ConversationHandler.END


async def handle_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка ввода имени пользователя."""
    chat_id = str(update.effective_chat.id)
    name = update.message.text.strip()
    
    if len(name) < 2:
        await update.message.reply_text("Имя должно содержать минимум 2 символа. Попробуйте еще раз:", parse_mode='HTML')
        return WAITING_FOR_NAME
    
    user = create_user(chat_id, name)
    user_logger = get_user_logger(chat_id, name)
    user_logger.info(f"Создан новый пользователь с именем {name}")
    
    await update.message.reply_text(
        f"Отлично, {name}! Я создал для вас нового пользователя.",
        parse_mode='HTML'
    )
    
    # Создаём новый поток
    client = context.application.bot_data["openai_client"]
    thread = client.beta.threads.create()
    user["thread_id"] = thread.id
    save_data(USERS_FILE, users)
    user_logger.info("Создан новый поток (thread) для пользователя")
    
    await update.message.reply_text("Создал новый поток (thread) для вашего пользователя.", parse_mode='HTML')
    await update.message.reply_text(f"Ваш баланс: {user['balance']} кредитов.", parse_mode='HTML')
    
    return ConversationHandler.END


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка любого текстового сообщения (не команды)."""
    chat_id = str(update.effective_chat.id)
    user = get_user(chat_id)

    if not user:
        # Если пользователь не существует, перенаправляем на /start
        await update.message.reply_text("Для начала введите /start", parse_mode='HTML')
        return

    user_logger = get_user_logger(chat_id, user["name"])
    user_logger.info(f"Получено сообщение: {update.message.text}")

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
    user_logger.info("Запускаю ассистента...")
    messages = await run_assistant(
        client=client,
        thread_id=user["thread_id"],
        assistant_id=ASSISTANT_ID,
        user_id=chat_id,
        context=context
    )

    # Подробное логирование результатов
    user_logger.info(f"Получено {len(messages)} сообщений от ассистента")
    if not messages:
        user_logger.warning("Ассистент вернул пустой список сообщений")
        await update.message.reply_text("❌ ОШИБКА: Ассистент не смог обработать ваш запрос. Попробуйте еще раз через несколько секунд.", parse_mode='HTML')
        return

    # Если вернулся объект с ошибкой
    if isinstance(messages, list) and len(messages) == 1 and isinstance(messages[0], dict) and "error" in messages[0]:
        user_logger.error(messages[0]["error"])
        await update.message.reply_text(messages[0]["error"], parse_mode='HTML')
        return

    # Отправляем все подряд идущие сообщения ассистента (от старого к новому)
    for msg in messages:
        user_logger.info(f"Отправляю ответ пользователю: {msg.content}...")
        if msg.content and isinstance(msg.content, list):
                if len(msg.content) > 0:
                    assistant_text = msg.content[0].text.value
                    user_logger.info(f"Извлечен текст из content[0]: {assistant_text}...")
                else:
                    user_logger.warning("content является пустым списком")
        else:
            assistant_text = str(msg.content)
            user_logger.info(f"Извлечен текст напрямую: {assistant_text}...")
        
        # Преобразуем **жирный** в <b>жирный</b> для совместимости
        text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', assistant_text)
        await update.message.reply_text(text, parse_mode='HTML')


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработка неизвестных команд."""
    await update.message.reply_text("Извините, я не знаю такой команды.", parse_mode='HTML')


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

    # Создаем ConversationHandler для обработки команды /start и ввода имени
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", cmd_start)],
        states={
            WAITING_FOR_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_name)],
        },
        fallbacks=[CommandHandler("start", cmd_start)]
    )

    # Регистрируем хендлеры
    application.add_handler(conv_handler)
    # Текстовые сообщения (не команды)
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_text_message))
    # Хендлер для неизвестных команд
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    # Запускаем бота
    application.run_polling()


if __name__ == "__main__":
    main()

