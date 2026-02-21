with open('bot.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Добавляем функцию отправки с кнопками после функции tg_send
old_tg_send = '''def tg_get_file_bytes(file_id):'''
new_tg_send = '''def tg_send_with_menu(chat_id, text):
    keyboard = {"keyboard": [[{"text": "\\U0001f3e0 Старт"}, {"text": "\\U0001f4e6 Аптечка"}], [{"text": "\\U0001f48a Курсы приёма"}, {"text": "\\U0001f468\\u200d\\U0001f469\\u200d\\U0001f467\\u200d\\U0001f466 Семья"}]], "resize_keyboard": True, "one_time_keyboard": False}
    return tg_api("sendMessage", {"chat_id": chat_id, "text": text, "reply_markup": keyboard})

def tg_get_file_bytes(file_id):'''
text = text.replace(old_tg_send, new_tg_send)

# 2. В /start заменяем tg_send на tg_send_with_menu
old_start_send = '            tg_send(chat_id, welcome)\n            return\n        if user_text.strip() == "/reminders":'
new_start_send = '            tg_send_with_menu(chat_id, welcome)\n            return\n        if user_text.strip() == "/reminders":'
text = text.replace(old_start_send, new_start_send)

# 3. Добавляем обработку кнопок - перед "else: return"
old_else_return = '    else:\n        return\n    save_message'
new_else_return = '''    else:
        return
    if user_text == "\\U0001f3e0 Старт":
        user_text = "/start"
    elif user_text == "\\U0001f4e6 Аптечка":
        user_text = "/inventory"
    elif user_text == "\\U0001f48a Курсы приёма":
        user_text = "/reminders"
    elif user_text == "\\U0001f468\\u200d\\U0001f469\\u200d\\U0001f467\\u200d\\U0001f466 Семья":
        user_text = "/family"
    save_message'''
text = text.replace(old_else_return, new_else_return)

with open('bot.py', 'w', encoding='utf-8') as f:
    f.write(text)
print('Step 3 done - menu buttons added!')