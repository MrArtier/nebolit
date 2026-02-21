with open('bot.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Исправляем: end_date = None если course_days = 0 (бессрочно)
old_end = '                end = start + timedelta(days=course_days) if course_days > 0 else None'
new_end = '                end = start + timedelta(days=course_days) if course_days > 0 else None\n                total_pills = 0 if course_days == 0 else total_pills'
text = text.replace(old_end, new_end)

# Обновляем отображение в /reminders - показываем "бессрочно" если course_days = 0
old_course_display = '''                            if r[5] and r[5] > 0:
                                line += "\\n   \\U0001f4c5 Курс: %s дней (%s - %s)" % (r[5], r[6], r[7])'''
new_course_display = '''                            if r[5] and r[5] > 0:
                                line += "\\n   \\U0001f4c5 Курс: %s дней (%s - %s)" % (r[5], r[6], r[7])
                            elif r[5] == 0 or r[5] is None:
                                line += "\\n   \\U0001f504 Бессрочный приём"'''
text = text.replace(old_course_display, new_course_display)

# Обновляем контекст для GPT - показываем "бессрочно"
old_rem_ctx = '''                    rlines.append("- %s %s, приём: %s %s, курс: %s дней, осталось табл: %s" % (r[1], ("для "+r[0]) if r[0] else "", r[3], r[4] or "", r[5] or "?", int(r[8]) if r[8] else "?"))'''
new_rem_ctx = '''                    course_str = "бессрочно" if (r[5] == 0 or r[5] is None) else "%s дней" % r[5]
                    in_stock = "нет в аптечке"
                    c3 = conn2.cursor()
                    c3.execute("SELECT quantity FROM inventory WHERE user_id = %s AND LOWER(medicine_name) = LOWER(%s)", (uid, r[1]))
                    stock_row = c3.fetchone()
                    if stock_row:
                        in_stock = "в аптечке: %s шт" % stock_row[0]
                    rlines.append("- %s %s, приём: %s %s, курс: %s, %s" % (r[1], ("для "+r[0]) if r[0] else "", r[3], r[4] or "", course_str, in_stock))'''
text = text.replace(old_rem_ctx, new_rem_ctx)

with open('bot.py', 'w', encoding='utf-8') as f:
    f.write(text)
print('Step 2 done - endless reminders + stock check!')