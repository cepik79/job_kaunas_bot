import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from bs4 import BeautifulSoup
import requests
import os

# Токен берем из Environment Variables
BOT_TOKEN = os.getenv('BOT_TOKEN')
bot = telebot.TeleBot(BOT_TOKEN)

# Параметры поиска по умолчанию
search_params = {
    "city": "Kaunas",
    "title": "",
    "no_experience": False,
    "ukrainians": False,
    "no_lithuanian": False,
    "no_english": False,
    "sites": ["cvonline", "cvbankas", "jobservice"]  # список сайтов
}

# Словарь с сайтами и ссылками
sites_urls = {
    "cvonline": "https://www.cvonline.lt/jobs",
    "cvbankas": "https://www.cvbankas.lt/jobs",
    "jobservice": "https://www.jobservice.lt/jobs"
}

# Меню настроек фильтров
def get_filters_markup():
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    markup.add(
        InlineKeyboardButton(f"Без опыта: {'✔' if search_params['no_experience'] else '❌'}", callback_data="toggle_no_experience"),
        InlineKeyboardButton(f"Берут украинцев: {'✔' if search_params['ukrainians'] else '❌'}", callback_data="toggle_ukrainians")
    )
    markup.row(
        InlineKeyboardButton(f"Без литовского: {'✔' if search_params['no_lithuanian'] else '❌'}", callback_data="toggle_no_lithuanian"),
        InlineKeyboardButton(f"Без английского: {'✔' if search_params['no_english'] else '❌'}", callback_data="toggle_no_english")
    )
    markup.row(
        InlineKeyboardButton("Выбрать сайты", callback_data="choose_sites"),
        InlineKeyboardButton("Назад", callback_data="back")
    )
    return markup

# Меню выбора сайтов
def get_sites_markup():
    markup = InlineKeyboardMarkup()
    markup.row_width = 2
    for site in sites_urls.keys():
        status = '✔' if site in search_params['sites'] else '❌'
        markup.add(InlineKeyboardButton(f"{site} {status}", callback_data=f"toggle_site_{site}"))
    markup.add(InlineKeyboardButton("Назад", callback_data="back"))
    return markup

# Команда /start
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, "Привет! Настрой параметры поиска вакансий:", reply_markup=get_filters_markup())

# Обработка кнопок
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    if call.data.startswith("toggle_"):
        key = call.data.replace("toggle_", "")
        if key in search_params:
            search_params[key] = not search_params[key]
        elif key.startswith("site_"):
            site = key.replace("site_", "")
            if site in search_params['sites']:
                search_params['sites'].remove(site)
            else:
                search_params['sites'].append(site)
        bot.edit_message_text("Настрой параметры поиска вакансий:", call.message.chat.id, call.message.message_id, reply_markup=get_filters_markup() if "site" not in key else get_sites_markup())
    
    elif call.data == "choose_sites":
        bot.edit_message_text("Выбери сайты для поиска:", call.message.chat.id, call.message.message_id, reply_markup=get_sites_markup())
    
    elif call.data == "back":
        bot.edit_message_text("Настрой параметры поиска вакансий:", call.message.chat.id, call.message.message_id, reply_markup=get_filters_markup())

# Получение вакансий (пример парсинга одного сайта)
def get_vacancies(site, title, city):
    url = sites_urls.get(site)
    results = []
    if site == "cvonline":
        # Простейший пример: отправляем запрос и парсим HTML
        r = requests.get(url, params={"q": title, "location": city})
        soup = BeautifulSoup(r.text, "html.parser")
        jobs = soup.find_all("div", class_="job-item")  # пример
        for job in jobs[:5]:  # максимум 5 вакансий
            name = job.find("h2").text.strip()
            link = job.find("a")["href"]
            results.append(f"{name}\n{link}")
    # TODO: добавить остальные сайты с их структурами
    return results

# Команда поиска
@bot.message_handler(commands=['search'])
def search(message):
    bot.send_message(message.chat.id, "Введите название вакансии:")
    bot.register_next_step_handler(message, process_search)

def process_search(message):
    search_params["title"] = message.text
    all_results = []
    for site in search_params['sites']:
        all_results.extend(get_vacancies(site, search_params['title'], search_params['city']))
    if all_results:
        bot.send_message(message.chat.id, "\n\n".join(all_results))
    else:
        bot.send_message(message.chat.id, "Вакансий не найдено.")

# Запуск бота
bot.polling(none_stop=True)

