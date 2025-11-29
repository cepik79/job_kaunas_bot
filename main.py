import telebot

BOT_TOKEN = "8564311433:AAHvOhXpaj6Oxde6lCIpOXLUzG5k9DkSU9c"


bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "Бот работает! 👍")

bot.polling(none_stop=True)
