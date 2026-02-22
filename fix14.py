with open('bot.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Добавляем функцию отправки с одной большой кнопкой для первого входа
old_tg_send_with_menu = 'def tg_send_with_menu(chat_id, text):'
new_tg_send_with_menu = '''def tg_send_start_button(chat_id):
    keyboard = {"keyboard": [[{"text": "\\U0001f4aa Навести порядок"}]], "resize_keyboard": True, "one_time_keyboard": True}
    return tg_api("sendMessage", {"chat_id": chat_id, "text": "\\U0001f48a Добро пожаловать в НеБолит!\\n\\nНажми кнопку ниже, чтобы начать \\U0001f447", "reply_markup": keyboard})

def tg_send_with_menu(chat_id, text):'''
text = text.replace(old_tg_send_with_menu, new_tg_send_with_menu)

# Добавляем обработку кнопки "Навести порядок"
old_cabinets_btn = '''    elif user_text == "\\U0001f3e0 Аптечки":
        user_text = "/cabinets"'''
new_cabinets_btn = '''    elif user_text == "\\U0001f3e0 Аптечки":
        user_text = "/cabinets"
    elif user_text == "\\U0001f4aa Навести порядок":
        user_text = "/start"'''
text = text.replace(old_cabinets_btn, new_cabinets_btn)

# Проверяем первый вход — если у пользователя нет истории, показываем кнопку
old_save_user = '    save_user(uid, uname)'
new_save_user = '''    is_new = False
    conn_check = get_db_connection()
    if conn_check:
        try:
            c_check = conn_check.cursor()
            c_check.execute("SELECT COUNT(*) FROM messages WHERE user_id = %s", (uid,))
            msg_count = c_check.fetchone()[0]
            if msg_count == 0:
                is_new = True
        except:
            pass
        finally:
            conn_check.close()
    save_user(uid, uname)
    if is_new and not ("text" in msg and msg["text"].strip() == "/start"):
        tg_send_start_button(chat_id)
        return'''
text = text.replace(old_save_user, new_save_user)

with open('bot.py', 'w', encoding='utf-8') as f:
    f.write(text)
print('Done fix14!')