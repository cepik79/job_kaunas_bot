import telebot

BOT_TOKEN =8252969262:AAGRyG-A_ZtQVSqSVbKGzF35e7WjqStozkY 

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, "Бот работает! 👍")

bot.polling(none_stop=True)
