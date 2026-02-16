import telebot
from telebot import types
import re

bot = telebot.TeleBot('') #ключ тг бота
support_id = 6792288392 #id tg support 
user_message = ''

#Команда обработки поддержки
@bot.message_handler(commands=['start'])
def support(message):
    global user_message
    msg = bot.send_message(message.chat.id, 'Напишите сообщение в поддержку: ')
    bot.register_next_step_handler(msg, get_user_message)

def get_user_message(message):
    global user_message
    user_message = message.text
    user_id = message.chat.id
    user_name = message.from_user.first_name
    
    keyboard = types.InlineKeyboardMarkup(row_width=1)
    answer = types.InlineKeyboardButton(text="Ответить", callback_data=f"answer_{user_id}")
    keyboard.add(answer)
    
    bot.send_message(
        support_id,
        f"Сообщение от {user_name} (ID: {user_id}):\n{user_message}",
        reply_markup=keyboard
    )
    
    bot.send_message(
        message.chat.id,
        "Ваше сообщение отправлено в поддержку"
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith('answer_'))
def answer_callback(call):
    user_id = int(call.data.split('_')[1])
    msg = bot.send_message(
        support_id,
        "Напишите ответ:",
        reply_markup=types.ForceReply()
    )
    bot.register_next_step_handler(msg, send_answer, user_id)

def send_answer(message, user_id):
    bot.send_message(
        user_id,
        f"Ответ от поддержки:\n{message.text}"
    )
    bot.send_message(support_id, "Ответ отправлен")

@bot.message_handler(func=lambda message: message.chat.id == support_id)
def seller_reply(message):
    if message.reply_to_message:
        match = re.search(r'ID: (\d+)', message.reply_to_message.text)
        if match:
            user_id = int(match.group(1))
            bot.send_message(
                user_id,
                f"Ответ от поддержки:\n{message.text}"
            )
            bot.send_message(support_id, "Ответ отправлен")

if __name__ == '__main__':
    bot.infinity_polling()
