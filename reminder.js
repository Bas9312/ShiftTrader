function listUpcomingEvents() {
    const calendarId = 'fff294e6c8e16f7ab80322a14ac614b849423a1877d7bd27b7e32167b9350d02@group.calendar.google.com';
    
    const optionalArgs = {
      timeMin: (new Date()).toISOString(),
      showDeleted: false,
      singleEvents: true,
      maxResults: 50, // Берём больше, чтобы захватить всю неделю
      orderBy: 'startTime'
    };
    
    try {
      const response = Calendar.Events.list(calendarId, optionalArgs);
      const events = response.items;
      
      if (!events || events.length === 0) {
        console.log('No upcoming events found');
        return;
      }
      
      const eventsToday = [];
      const eventsTomorrow = [];
      const eventsThisWeek = [];
  
      const now = new Date();
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      const tomorrow = new Date(today);
      tomorrow.setDate(tomorrow.getDate() + 1);
  
      const weekStart = new Date(today);
      const weekEnd = new Date(today);
      weekEnd.setDate(weekStart.getDate() + 6); // До воскресенья включительно
  
      function isSameDay(d1, d2) {
        return d1.getFullYear() === d2.getFullYear() &&
               d1.getMonth() === d2.getMonth() &&
               d1.getDate() === d2.getDate();
      }
  
      function isSameWeek(date) {
        return date >= weekStart && date <= weekEnd;
      }
  
      function getMentions(text) {
        const mentionMap = {
          'Тари': '@gtariell',
          'Женя': '@onemorevkpage',
          'Бас': '@bas9312',
          'Анте': '@id138553942',
          'Коля': '@dum2121'
        };
        
        const mentions = [];
        for (let name in mentionMap) {
          if (text.includes(name)) {
            mentions.push(mentionMap[name]);
          }
        }
        return mentions.length > 0 ? mentions.join(' ') : '';
      }
  
      for (const event of events) {
        let startTime = event.start.dateTime || event.start.date;
        const eventDate = new Date(startTime);
  
        if (isSameDay(eventDate, today)) {
          eventsToday.push(event);
        } else if (isSameDay(eventDate, tomorrow)) {
          eventsTomorrow.push(event);
        }
        
        if (isSameWeek(eventDate)) {
          eventsThisWeek.push(event);
        }
  
        console.log('%s (%s)', event.summary, startTime);
      }
  
      if (eventsToday.length > 0) {
        let messageToday = '🔔 Напоминание!\nСегодня запланированы события:\n';
        for (const evt of eventsToday) {
          const mentions = getMentions(evt.summary);
          messageToday += `\n• ${evt.summary} ${mentions}`;
        }
        sendMessageWithCat(messageToday);
      }
  
      if (eventsTomorrow.length > 0) {
        let messageTomorrow = '📅 Завтра будет:\n';
        for (const evt of eventsTomorrow) {
          const mentions = getMentions(evt.summary);
          messageTomorrow += `\n• ${evt.summary} ${mentions}`;
        }
        sendMessageWithCat(messageTomorrow);
      }
  
      const isMonday = today.getDay() === 1;
      if (isMonday && eventsThisWeek.length > 0) {
        let messageWeek = '📅 План на неделю:\n';
        for (const evt of eventsThisWeek) {
          const eventDate = new Date(evt.start.dateTime || evt.start.date);
          const day = eventDate.toLocaleDateString('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' });
          const mentions = getMentions(evt.summary);
          messageWeek += `\n• ${day}: ${evt.summary} ${mentions}`;
        }
        sendMessageWithCat(messageWeek);
      }
  
    } catch (err) {
      console.log('Failed with error %s', err.message);
    }
  }
  
  const ACCESS_TOKEN = 'vk1.a.nDaQKz4eMxltP1pHuRZh3y5GH-g2k7lBbnm30RxeEl50dDs1snwacR5TWU_G7ZEX_uFlIvamLgxpF63u3eefYEFpKz-w2g_ETZE88VDD8OVkIPnQkjnvbNy5sW2p7gBjMw5n7lWUCMTYDm-7eYi90JoWG0KoulcGS60NFxz5Q4PTsl1HRRmDVlEycfXE1wl5p-IpWAVwcNXLtzXqqn7TDQ'
  
  function sendMessageWithCat(message) {
    try {
      const catResponse = UrlFetchApp.fetch('https://api.thecatapi.com/v1/images/search');
      const catJson = JSON.parse(catResponse.getContentText());
      const catUrl = catJson && catJson.length > 0 ? catJson[0].url : '';
      
      if (catUrl) {
        const attachment = uploadPhotoToVK(catUrl);
        sendMessageToVK(message, attachment);
      } else {
        sendMessageToVK(message, '');
      }
    } catch (error) {
      console.log('Failed to fetch cat image:', error);
      sendMessageToVK(message, '');
    }
  }
  
  function uploadPhotoToVK(imageUrl) {
    try {
      // 1. Получаем сервер для загрузки фото
      const uploadServerResponse = UrlFetchApp.fetch('https://api.vk.com/method/photos.getMessagesUploadServer?v=5.199&access_token=' + ACCESS_TOKEN);
      const uploadServerJson = JSON.parse(uploadServerResponse.getContentText());
      
      if (!uploadServerJson.response || !uploadServerJson.response.upload_url) {
        console.log('❌ Ошибка: Не удалось получить upload_url');
        console.log('Ответ VK API:', uploadServerResponse.getContentText());
        return '';
      }
  
      const uploadUrl = uploadServerJson.response.upload_url;
  
      // 2. Загружаем фото
      const imageResponse = UrlFetchApp.fetch(imageUrl);
      const imageBlob = imageResponse.getBlob();
      
      const uploadResponse = UrlFetchApp.fetch(uploadUrl, {
        method: 'POST',
        payload: { file: imageBlob }
      });
  
      const uploadJson = JSON.parse(uploadResponse.getContentText());
  
      if (!uploadJson.photo || !uploadJson.server || !uploadJson.hash) {
        console.log('❌ Ошибка: Не удалось загрузить фото');
        console.log('Ответ VK API:', uploadResponse.getContentText());
        return '';
      }
  
      // 3. Преобразуем `server` в int64
      const serverInt = Math.floor(uploadJson.server);
      console.log('serverInt ', serverInt);
      console.log('Тип serverInt:', typeof serverInt, 'Значение:', serverInt);
  
      // 4. Сохраняем фото
  const formData = `v=5.199&photo=${encodeURIComponent(uploadJson.photo)}&server=${encodeURIComponent(String(Math.floor(uploadJson.server)))}&hash=${encodeURIComponent(uploadJson.hash)}`;
  
  const savePhotoResponse = UrlFetchApp.fetch('https://api.vk.ru/method/photos.saveMessagesPhoto', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${ACCESS_TOKEN}`,
      'Content-Type': 'application/x-www-form-urlencoded'
    },
    payload: formData
  });
    console.log('Save photo request sended ' + savePhotoResponse);
  
      const savePhotoJson = JSON.parse(savePhotoResponse.getContentText());
  
      if (!savePhotoJson.response || savePhotoJson.response.length === 0) {
        console.log('❌ Ошибка: Не удалось сохранить фото');
        console.log('Ответ VK API:', savePhotoResponse.getContentText());
        return '';
      }
  
      const photo = savePhotoJson.response[0];
      return `photo${photo.owner_id}_${photo.id}`;
      
    } catch (error) {
      console.log('❌ Исключение при загрузке фото:', error);
      return '';
    }
  }
  
  
  
  
  function sendMessageToVK(message, attachment) {
    const baseUrl = 'https://api.vk.com/method/messages.send';
    const params = {
      v: '5.199',
      access_token: ACCESS_TOKEN,
      random_id: Math.floor(Math.random() * 100000),
      peer_id: 2000000001,
      message: message
    };
  
    if (attachment) {
      params.attachment = attachment;
    }
  
    const fullUrl = `${baseUrl}?v=${params.v}&access_token=${params.access_token}&random_id=${params.random_id}&peer_id=${params.peer_id}&message=${encodeURIComponent(params.message)}${attachment ? `&attachment=${attachment}` : ''}`;
  
    const response = UrlFetchApp.fetch(fullUrl);
    console.log('VK response:', response.getContentText());
  }
  