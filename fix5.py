with open('bot.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Добавляем регулярку для напоминаний после ADD_FAM_RE
old_re = 'ADD_FAM_RE = r"\
\[ADD_FAMILY:(.+?)\\]"'
new_re = '''ADD_FAM_RE = r"\
\[ADD_FAMILY:(.+?)\\]"
ADD_REM_RE = r"\
\[ADD_REMINDER:(.+?)\\]"'''
text = text.replace(old_re, new_re)

# 2. Добавляем обработку ADD_REMINDER в process_gpt_commands перед conn.commit()
old_commit = '''        conn.commit()
    except Exception as e:
        logger.error("Cmd err: %s", e)'''

new_commit = '''        for rem in re.findall(ADD_REM_RE, text):
            parts = [p.strip() for p in rem.split("|")]
            member = parts[0] if len(parts) > 0 else ""
            medicine = parts[1] if len(parts) > 1 else ""
            schedule = parts[2] if len(parts) > 2 else "08:00"
            meal = parts[3] if len(parts) > 3 else ""
            dosage = parts[4] if len(parts) > 4 else ""
            course_days = 0
            if len(parts) > 5:
                try:
                    course_days = int(parts[5])
                except ValueError:
                    course_days = 0
            pills_per_dose = 1.0
            if len(parts) > 6:
                try:
                    pills_per_dose = float(parts[6])
                except ValueError:
                    pills_per_dose = 1.0
            pills_in_pack = 0
            if len(parts) > 7:
                try:
                    pills_in_pack = int(parts[7])
                except ValueError:
                    pills_in_pack = 0
            if medicine:
                from datetime import date, timedelta
                start = date.today()
                end = start + timedelta(days=course_days) if course_days > 0 else None
                times_per_day = len(schedule.split(","))
                total_pills = course_days * times_per_day * pills_per_dose if course_days > 0 else 0
                c.execute("INSERT INTO reminders (user_id, family_member, medicine_name, dosage, schedule_time, meal_relation, course_days, pills_per_dose, pills_in_pack, pills_remaining, start_date, end_date, active) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)", (uid, member, medicine, dosage, schedule, meal, course_days, pills_per_dose, pills_in_pack, total_pills, start, end))
        conn.commit()
    except Exception as e:
        logger.error("Cmd err: %s", e)'''
text = text.replace(old_commit, new_commit)

# 3. Добавляем очистку ADD_REMINDER в clean_commands
old_clean = '''    text = re.sub(ADD_FAM_RE, "", text)
    return text.strip()'''
new_clean = '''    text = re.sub(ADD_FAM_RE, "", text)
    text = re.sub(ADD_REM_RE, "", text)
    return text.strip()'''
text = text.replace(old_clean, new_clean)

# 4. Добавляем функции для напоминаний и команду /reminders перед обработкой /inventory
old_inventory = '''        if user_text.strip() == "/inventory":'''

new_inventory = '''        if user_text.strip() == "/reminders":
            conn = get_db_connection()
            if conn:
                try:
                    c = conn.cursor()
                    c.execute("SELECT family_member, medicine_name, dosage, schedule_time, meal_relation, course_days, start_date, end_date, pills_remaining FROM reminders WHERE user_id = %s AND active = TRUE ORDER BY schedule_time", (uid,))
                    rems = c.fetchall()
                    if rems:
                        lines = ["\\U0001f4cb Активные напоминания:\\n"]
                        for r in rems:
                            line = "\\U0001f48a %s" % r[1]
                            if r[0]:
                                line += " (для %s)" % r[0]
                            line += "\\n   \\U000023f0 %s" % r[3]
                            if r[4]:
                                line += " %s" % r[4]
                            if r[2]:
                                line += "\\n   \\U0001f4ca %s" % r[2]
                            if r[5] and r[5] > 0:
                                line += "\\n   \\U0001f4c5 Курс: %s дней (%s - %s)" % (r[5], r[6], r[7])
                            if r[8] and r[8] > 0:
                                line += "\\n   \\U0001f4a6 Осталось таблеток: %s" % int(r[8])
                            lines.append(line)
                        tg_send(chat_id, "\\n".join(lines))
                    else:
                        tg_send(chat_id, "Нет активных напоминаний.")
                except Exception as e:
                    logger.error("Reminders err: %s", e)
                    tg_send(chat_id, "Ошибка при загрузке напоминаний.")
                finally:
                    conn.close()
            else:
                tg_send(chat_id, "Ошибка подключения к базе.")
            return
        if user_text.strip() == "/inventory":'''
text = text.replace(old_inventory, new_inventory)

# 5. Добавляем информацию о напоминаниях в контекст для GPT
old_ctx = '    ctx = "Аптечка:\\n" + inv_text + "\\nСемья:\\n" + fam_text'
new_ctx = '''    rem_text = "Напоминаний нет."
    conn2 = get_db_connection()
    if conn2:
        try:
            c2 = conn2.cursor()
            c2.execute("SELECT family_member, medicine_name, dosage, schedule_time, meal_relation, course_days, start_date, end_date, pills_remaining FROM reminders WHERE user_id = %s AND active = TRUE", (uid,))
            rems = c2.fetchall()
            if rems:
                rlines = []
                for r in rems:
                    rlines.append("- %s %s, приём: %s %s, курс: %s дней, осталось табл: %s" % (r[1], ("для "+r[0]) if r[0] else "", r[3], r[4] or "", r[5] or "?", int(r[8]) if r[8] else "?"))
                rem_text = "\\n".join(rlines)
        except Exception as e:
            logger.error("Rem ctx err: %s", e)
        finally:
            conn2.close()
    ctx = "Аптечка:\\n" + inv_text + "\\nСемья:\\n" + fam_text + "\\nНапоминания:\\n" + rem_text'''
text = text.replace(old_ctx, new_ctx)

# 6. Добавляем /reminders в приветственное сообщение
old_commands = '"/inventory \\u2014 посмотреть аптечку\\n"'
new_commands = '"/inventory \\u2014 посмотреть аптечку\\n/reminders \\u2014 напоминания о приёме\\n"'
text = text.replace(old_commands, new_commands)

with open('bot.py', 'w', encoding='utf-8') as f:
    f.write(text)
print('Step 3 done - reminders fully added!')