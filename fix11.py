with open('bot.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Добавляем функцию конвертации Markdown в HTML после импортов
old_logging = 'logger = logging.getLogger(__name__)'
new_logging = '''logger = logging.getLogger(__name__)

def md_to_html(text):
    import re as _re
    text = _re.sub(r'\*\*\*(.+?)\*\*\*', r'<b><i>\\1</i></b>', text)
    text = _re.sub(r'\*\*(.+?)\*\*', r'<b>\\1</b>', text)
    text = _re.sub(r'\*(.+?)\*', r'<i>\\1</i>', text)
    text = _re.sub(r'__(.+?)__', r'<u>\\1</u>', text)
    text = _re.sub(r'`(.+?)`', r'<code>\\1</code>', text)
    return text'''
text = text.replace(old_logging, new_logging)

# 2. Обновляем tg_send чтобы поддерживал HTML
old_tg_send_func = 'def tg_send(chat_id, text):\n    return tg_api("sendMessage", {"chat_id": chat_id, "text": text})'
new_tg_send_func = '''def tg_send(chat_id, text):
    html_text = md_to_html(text)
    try:
        return tg_api("sendMessage", {"chat_id": chat_id, "text": html_text, "parse_mode": "HTML"})
    except:
        return tg_api("sendMessage", {"chat_id": chat_id, "text": text})'''
text = text.replace(old_tg_send_func, new_tg_send_func)

# 3. Обновляем tg_send_with_menu тоже
old_menu_func = '''def tg_send_with_menu(chat_id, text):
    keyboard = {"keyboard": [[{"text": "\\U0001f3e0 Старт"}, {"text": "\\U0001f4e6 Аптечка"}], [{"text": "\\U0001f48a Курсы приёма"}, {"text": "\\U0001f468\\u200d\\U0001f469\\u200d\\U0001f467\\u200d\\U0001f466 Семья"}]], "resize_keyboard": True, "one_time_keyboard": False}
    return tg_api("sendMessage", {"chat_id": chat_id, "text": text, "reply_markup": keyboard})'''
new_menu_func = '''def tg_send_with_menu(chat_id, text):
    keyboard = {"keyboard": [[{"text": "\\U0001f3e0 Старт"}, {"text": "\\U0001f4e6 Аптечка"}], [{"text": "\\U0001f48a Курсы приёма"}, {"text": "\\U0001f468\\u200d\\U0001f469\\u200d\\U0001f467\\u200d\\U0001f466 Семья"}]], "resize_keyboard": True, "one_time_keyboard": False}
    html_text = md_to_html(text)
    try:
        return tg_api("sendMessage", {"chat_id": chat_id, "text": html_text, "parse_mode": "HTML", "reply_markup": keyboard})
    except:
        return tg_api("sendMessage", {"chat_id": chat_id, "text": text, "reply_markup": keyboard})'''
text = text.replace(old_menu_func, new_menu_func)

with open('bot.py', 'w', encoding='utf-8') as f:
    f.write(text)
print('Done!')