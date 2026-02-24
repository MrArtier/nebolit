# fix_family.py - чистим шаблоны семьи и добавляем диагностику
with open("bot.py", "r", encoding="utf-8") as f:
    code = f.read()

# 1. Добавить диагностику семьи в debug_db
old_debug = '''        c.execute("SELECT * FROM inventory ORDER BY id DESC LIMIT 3")
        recent = c.fetchall()
        return "DB OK. Users: %s, Msgs: %s, Inv: %s\\nColumns: %s\\nRecent: %s" % (users, msgs, inv, col_str, str(recent)), 200'''

new_debug = '''        c.execute("SELECT * FROM inventory ORDER BY id DESC LIMIT 3")
        recent = c.fetchall()
        c.execute("SELECT COUNT(*) FROM family")
        fam_count = c.fetchone()[0]
        c.execute("SELECT * FROM family ORDER BY id DESC LIMIT 10")
        fam_recent = c.fetchall()
        c.execute("SELECT content FROM messages WHERE content LIKE '%%ADD_FAMILY%%' ORDER BY id DESC LIMIT 5")
        fam_msgs = c.fetchall()
        return "DB OK. Users: %s, Msgs: %s, Inv: %s\\nColumns: %s\\nRecent inv: %s\\n\\nFamily: %s\\nRecent fam: %s\\nFam cmds in msgs: %s" % (users, msgs, inv, col_str, str(recent), fam_count, str(fam_recent), str(fam_msgs)), 200'''
code = code.replace(old_debug, new_debug)

# 2. Усилить очистку шаблонов при init_db
old_fam_clean = '''        c.execute("DELETE FROM family WHERE name IN ('имя','name','test') OR gender IN ('пол','gender') OR relation IN ('отношение','relation')")'''
new_fam_clean = '''        c.execute("DELETE FROM family WHERE name IN ('имя','name','test','член_семьи','member') OR gender IN ('пол','gender') OR relation IN ('отношение','relation','родство') OR age = 0")'''
code = code.replace(old_fam_clean, new_fam_clean)

# 3. Добавить fallback для ADD_FAMILY (как сделали для ADD_MEDICINE)
old_fallback_end = '''        process_gpt_commands(uid, reply)
        return clean_commands(reply)'''

new_fallback_end = '''        # Если GPT не включил команду ADD_FAMILY но явно добавляет члена семьи
        if "[ADD_FAMILY:" not in reply and any(w in reply.lower() for w in ["добавил", "добавила", "записал", "добавляю", "внёс", "внес"]):
            if any(w in reply.lower() for w in ["семь", "член", "родствен", "ребён", "ребен", "муж", "жен", "сын", "дочь", "мам", "пап", "бабушк", "дедушк"]):
                logger.info("GPT forgot ADD_FAMILY command, checking text")
                import re as _re2
                # Ищем имя в жирном
                name_m = _re2.search(r'\\*\\*(.+?)\\*\\*', reply)
                if name_m:
                    fam_name = name_m.group(1)
                    age_m = _re2.search(r'(\\d+)\\s*(?:лет|год|года)', reply)
                    age = age_m.group(1) if age_m else ""
                    gender = ""
                    if any(w in reply.lower() for w in ["жена", "дочь", "мама", "бабушка", "сестра", "девочка"]): gender = "Ж"
                    elif any(w in reply.lower() for w in ["муж", "сын", "папа", "дедушка", "брат", "мальчик"]): gender = "М"
                    relation = ""
                    for rel_word, rel_val in [("жена","жена"),("муж","муж"),("сын","сын"),("дочь","дочь"),("мама","мама"),("папа","папа"),("бабушка","бабушка"),("дедушка","дедушка"),("брат","брат"),("сестра","сестра"),("ребёнок","ребёнок"),("ребенок","ребёнок")]:
                        if rel_word in reply.lower():
                            relation = rel_val
                            break
                    cmd = "[ADD_FAMILY:%s|%s|%s|%s]" % (fam_name, age, gender, relation)
                    logger.info("Fallback FAMILY command: %s", cmd)
                    reply += "\\n" + cmd

        process_gpt_commands(uid, reply)
        return clean_commands(reply)'''
code = code.replace(old_fallback_end, new_fallback_end)

# 4. Усилить промпт для семьи
old_family_prompt = 'Аналогично для удаления ОБЯЗАТЕЛЬНО используй [REMOVE_MEDICINE:название], для семьи [ADD_FAMILY:...], для напоминаний [ADD_REMINDER:...]."""'
new_family_prompt = '''Аналогично для удаления ОБЯЗАТЕЛЬНО используй [REMOVE_MEDICINE:название].
Для добавления члена семьи ОБЯЗАТЕЛЬНО используй [ADD_FAMILY:имя|возраст|пол|отношение]. Пример: [ADD_FAMILY:Анна|30|Ж|жена]
Для напоминаний ОБЯЗАТЕЛЬНО используй [ADD_REMINDER:...].
НИКОГДА не используй шаблонные значения типа "имя", "возраст", "пол", "отношение" - только реальные данные от пользователя!"""'''
code = code.replace(old_family_prompt, new_family_prompt)

# 5. Добавить защиту от шаблонных значений в process_gpt_commands для family
old_fam_insert = '''            if name:
                c.execute("INSERT INTO family (user_id, name, age, gender, relation) VALUES (%s,%s,%s,%s,%s)", (uid, name, age, gender, relation))'''
new_fam_insert = '''            # Проверка на шаблонные значения
            bad_values = ['имя', 'name', 'test', 'член_семьи', 'member', 'пол', 'gender', 'отношение', 'relation', 'возраст']
            if name and name.lower() not in bad_values:
                if gender and gender.lower() in bad_values: gender = None
                if relation and relation.lower() in bad_values: relation = None
                # Проверяем дубликат
                c.execute("SELECT id FROM family WHERE user_id = %s AND LOWER(name) = LOWER(%s)", (uid, name))
                existing = c.fetchone()
                if existing:
                    c.execute("UPDATE family SET age=%s, gender=%s, relation=%s WHERE id=%s", (age, gender, relation, existing[0]))
                    logger.info("Updated family member: %s for user %s", name, uid)
                else:
                    c.execute("INSERT INTO family (user_id, name, age, gender, relation) VALUES (%s,%s,%s,%s,%s)", (uid, name, age, gender, relation))
                    logger.info("Added family member: %s for user %s", name, uid)'''
code = code.replace(old_fam_insert, new_fam_insert)

with open("bot.py", "w", encoding="utf-8") as f:
    f.write(code)

print("Family fixes applied!")