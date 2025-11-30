import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

BOT_TOKEN = "8564311433:AAHvOhXpaj6Oxde6lCIpOXLUzG5k9DkSU9c"
bot = telebot.TeleBot(BOT_TOKEN)

# Хранилище настроек
user_settings = {}

def main_menu():
    menu = ReplyKeyboardMarkup(resize_keyboard=True)
    menu.add(KeyboardButton("🔍 Поиск вакансий"))
    menu.add(KeyboardButton("⚙ Настройки поиска"))
    menu.add(KeyboardButton("🧩 Фильтры"))
    menu.add(KeyboardButton("📬 Авто уведомления"))
    return menu

def filters_menu(settings):
    menu = ReplyKeyboardMarkup(resize_keyboard=True)
    menu.add(KeyboardButton(f"Без опыта: {'ВКЛ' if settings['no_experience'] else 'ВЫКЛ'}"))
    menu.add(KeyboardButton(f"Берут украинцев: {'ВКЛ' if settings['ukrainians'] else 'ВЫКЛ'}"))
    menu.add(KeyboardButton(f"Без литовского: {'ВКЛ' if settings['no_lt'] else 'ВЫКЛ'}"))
    menu.add(KeyboardButton(f"Без английского: {'ВКЛ' if settings['no_en'] else 'ВЫКЛ'}"))
    menu.add(KeyboardButton("⬅ Назад"))
    return menu

@bot.message_handler(commands=['start'])
def start(message):
    user_settings[message.chat.id] = {
        "city": "Kaunas",
        "job": None,
        "salary": None,
        "schedule": None,
        "auto": False,

        # Новые фильтры
        "no_experience": False,
        "ukrainians": False,
        "no_lt": False,
        "no_en": False
    }

    bot.send_message(
        message.chat.id,
        "Привет! 👋\nБот ищет вакансии.\nВыбери действие:",
        reply_markup=main_menu()
    )

@bot.message_handler(func=lambda m: True)
def handler(message):
    chat_id = message.chat.id
    text = message.text
    settings = user_settings.get(chat_id)

    # Главное меню
    if text == "🔍 Поиск вакансий":
        bot.send_message(chat_id, "Поиск вакансий... (скоро подключим сайты)")        

    elif text == "⚙ Настройки поиска":
        bot.send_message(chat_id,
                         "Параметры, которые можно изменить:\n"
                         "- город\n- вакансия\n- зарплата\n- график\n"
                         "Напиши, что изменить.")

    # Включение меню фильтров
    elif text == "🧩 Фильтры":
        bot.send_message(chat_id, "Фильтры поиска:", reply_markup=filters_menu(settings))

    # Обработка фильтров
    elif text.startswith("Без опыта"):
        settings["no_experience"] = not settings["no_experience"]
        bot.send_message(chat_id, "Обновлено!", reply_markup=filters_menu(settings))

    elif text.startswith("Берут украинцев"):
        settings["ukrainians"] = not settings["ukrainians"]
        bot.send_message(chat_id, "Обновлено!", reply_markup=filters_menu(settings))

    elif text.startswith("Без литовского"):
        settings["no_lt"] = not settings["no_lt"]
        bot.send_message(chat_id, "Обновлено!", reply_markup=filters_menu(settings))

    elif text.startswith("Без английского"):
        settings["no_en"] = not settings["no_en"]
        bot.send_message(chat_id, "Обновлено!", reply_markup=filters_menu(settings))

    # Назад в меню
    elif text == "⬅ Назад":
        bot.send_message(chat_id, "Главное меню", reply_markup=main_menu())

    # Изменение города/вакансии/зарплаты/графика
    elif text.lower() in ["город", "city"]:
        bot.send_message(chat_id, "Введи город:")
        bot.register_next_step_handler(message, set_city)

    elif text.lower() in ["вакансия", "job"]:
        bot.send_message(chat_id, "Введи название вакансии:")
        bot.register_next_step_handler(message, set_job)

    elif text.lower() in ["зарплата", "salary"]:
        bot.send_message(chat_id, "Введи минимальную зарплату:")
        bot.register_next_step_handler(message, set_salary)

    elif text.lower() in ["график", "schedule"]:
        bot.send_message(chat_id, "Введи график:")
        bot.register_next_step_handler(message, set_schedule)

    # Авто уведомления
    elif text == "📬 Авто уведомления":
        settings["auto"] = not settings["auto"]
        bot.send_message(chat_id,
                         f"Автоматическая рассылка: {'ВКЛ' if settings['auto'] else 'ВЫКЛ'}",
                         reply_markup=main_menu())

def set_city(message):
    user_settings[message.chat.id]["city"] = message.text
    bot.send_message(message.chat.id, "Город обновлён!", reply_markup=main_menu())

def set_job(message):
    user_settings[message.chat.id]["job"] = message.text
    bot.send_message(message.chat.id, "Вакансия обновлена!", reply_markup=main_menu())

def set_salary(message):
    user_settings[message.chat.id]["salary"] = message.text
    bot.send_message(message.chat.id, "Зарплата обновлена!", reply_markup=main_menu())

def set_schedule(message):
    user_settings[message.chat.id]["schedule"] = message.text
    bot.send_message(message.chat.id, "График обновлён!", reply_markup=main_menu())

bot.polling(none_stop=True)

