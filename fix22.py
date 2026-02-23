with open('bot.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# 1. Удаляем блок кнопок со старого места (строки 979-990)
# и else: return (строки 977-978)
del_start = None
del_end = None
for i, l in enumerate(lines):
    if l.strip() == 'else:' and i > 970 and i < 980:
        del_start = i
    if 'save_message(uid, "user", user_text)' in l and i > 985:
        del_end = i
        break

if del_start and del_end:
    # Сохраняем блок кнопок
    button_lines = []
    for i in range(del_start, del_end):
        if 'user_text ==' in lines[i] or 'user_text = ' in lines[i] or lines[i].strip().startswith('elif'):
            button_lines.append(lines[i])
    
    # Удаляем строки от else:return до save_message (не включая save_message)
    del lines[del_start:del_end]

# 2. Находим место для вставки кнопок — ПЕРЕД проверкой подписки (перед "if uid == ADMIN_ID:")
# Ищем первое вхождение "if uid == ADMIN_ID:" в handle_update
insert_idx = None
for i, l in enumerate(lines):
    if 'if uid == ADMIN_ID:' in l and 'sub' not in l and 'admin' not in l.lower():
        insert_idx = i
        break

# Если не нашли, ищем "if user_text.strip() == \"/admin\""
if not insert_idx:
    for i, l in enumerate(lines):
        if 'if user_text.strip() == "/admin" and uid == ADMIN_ID:' in l:
            insert_idx = i
            break

if insert_idx:
    button_block = [
        '        if user_text == "\\U0001f3e0 Старт" or user_text == "\\U0001f4aa Навести порядок":\n',
        '            user_text = "/start"\n',
        '        elif user_text == "\\U0001f4e6 Аптечка":\n',
        '            user_text = "/inventory"\n',
        '        elif user_text == "\\U0001f48a Курсы приёма":\n',
        '            user_text = "/reminders"\n',
        '        elif user_text == "\\U0001f468\\u200d\\U0001f469\\u200d\\U0001f467\\u200d\\U0001f466 Семья":\n',
        '            user_text = "/family"\n',
        '        elif user_text == "\\U0001f3e0 Аптечки":\n',
        '            user_text = "/cabinets"\n',
    ]
    for j, bl in enumerate(button_block):
        lines.insert(insert_idx + j, bl)

with open('bot.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)
print('Done fix22!')