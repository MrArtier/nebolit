with open('bot.py', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Добавляем эндпоинт /yukassa в Flask
old_health = '@app.route("/health")'
new_health = '''@app.route("/yukassa", methods=["POST"])
def yukassa_webhook():
    try:
        data = request.get_json(force=True)
        event = data.get("event", "")
        obj = data.get("object", {})
        if event == "payment.succeeded":
            payment_id = obj.get("id", "")
            metadata = obj.get("metadata", {})
            user_id = int(metadata.get("user_id", 0))
            if user_id and payment_id:
                activate_subscription(user_id, 365, payment_id)
                conn_p = get_db_connection()
                if conn_p:
                    try:
                        c_p = conn_p.cursor()
                        c_p.execute("UPDATE payments SET status='succeeded', confirmed_at=CURRENT_TIMESTAMP WHERE payment_id=%s", (payment_id,))
                        conn_p.commit()
                    finally:
                        conn_p.close()
                tg_send(user_id, "\\u2705 Оплата прошла успешно! Подписка активирована на 1 год. Спасибо!")
        return "ok", 200
    except Exception as e:
        logger.error("YuKassa webhook err: %s", e)
        return "ok", 200

@app.route("/health")'''
text = text.replace(old_health, new_health)

# 2. Добавляем проверку подписки + промокод перед обработкой сообщений
# Ищем место после save_user и is_new проверки, перед обработкой /start
old_start_check = '        if user_text.strip() == "/start":'
new_start_check = '''        sub = get_subscription(uid)
        if user_text.strip().upper().startswith("NB-") or user_text.strip().upper().startswith("NEBOLIT"):
            promo = check_promo(user_text.strip())
            if promo:
                already_used = not use_promo(uid, promo["id"])
                if already_used:
                    tg_send(chat_id, "\\u274c Вы уже использовали этот промокод.")
                    return
                if promo["action"] == "discount":
                    price = int(SUBSCRIPTION_PRICE * (100 - promo["discount"]) / 100)
                    payment_id, pay_url = create_yukassa_payment(uid, price, "Подписка НеБолит (скидка %s%%)" % promo["discount"])
                    if pay_url:
                        conn_pr = get_db_connection()
                        if conn_pr:
                            try:
                                c_pr = conn_pr.cursor()
                                c_pr.execute("UPDATE payments SET promo_code=%s, discount_percent=%s WHERE payment_id=%s", (promo["code"], promo["discount"], payment_id))
                                conn_pr.commit()
                            finally:
                                conn_pr.close()
                        tg_send(chat_id, "\\U0001f389 Промокод принят! Скидка %s%%\\n\\U0001f4b0 Цена: %s \\u20bd (вместо %s \\u20bd)\\n\\n\\U0001f449 Оплатите по ссылке:\\n%s" % (promo["discount"], price, SUBSCRIPTION_PRICE, pay_url))
                    else:
                        tg_send(chat_id, "\\u274c Ошибка создания платежа. Попробуйте позже.")
                    return
                elif promo["action"] == "free_days":
                    activate_subscription(uid, promo["free_days"])
                    tg_send(chat_id, "\\U0001f389 Промокод принят! Вам подарено %s дней бесплатного доступа!" % promo["free_days"])
                    return
                elif promo["action"] == "full_free":
                    activate_subscription(uid, 365)
                    tg_send(chat_id, "\\U0001f389 Промокод принят! Подписка на год активирована бесплатно!")
                    return
            else:
                pass
        if user_text.strip() == "/subscribe":
            if sub["plan"] == "paid" and sub["active"]:
                tg_send(chat_id, "\\u2705 У вас уже есть активная подписка! Осталось дней: %s" % sub["days_left"])
                return
            payment_id, pay_url = create_yukassa_payment(uid, SUBSCRIPTION_PRICE)
            if pay_url:
                tg_send(chat_id, "\\U0001f48a Подписка НеБолит на 1 год\\n\\U0001f4b0 Стоимость: %s \\u20bd\\n\\n\\U0001f449 Оплатите по ссылке:\\n%s\\n\\nПосле оплаты доступ активируется автоматически!" % (SUBSCRIPTION_PRICE, pay_url))
            else:
                tg_send(chat_id, "\\u274c Ошибка создания платежа. Попробуйте позже.")
            return
        if user_text.strip() == "/status":
            if sub["plan"] == "paid":
                tg_send(chat_id, "\\u2705 Подписка активна! Осталось %s дней." % sub["days_left"])
            elif sub["plan"] == "trial":
                tg_send(chat_id, "\\U0001f552 Пробный период. Осталось %s дней.\\n\\nДля оплаты: /subscribe" % sub["days_left"])
            else:
                tg_send(chat_id, "\\u274c Подписка неактивна.\\n\\nДля оплаты: /subscribe")
            return
        if not sub["active"] and user_text.strip() not in ["/start", "/subscribe", "/status"]:
            is_free_query = any(w in user_text.lower() for w in ["что такое", "для чего", "от чего", "зачем", "описание", "инструкция", "побочные", "аналог"])
            if not is_free_query:
                if sub.get("trial"):
                    tg_send(chat_id, "\\u23f0 Пробный период закончился.\\n\\nВам доступны бесплатные справки о лекарствах. Для полного доступа оформите подписку: /subscribe")
                else:
                    tg_send(chat_id, "\\U0001f512 Эта функция доступна по подписке.\\n\\nВам доступны бесплатные справки о лекарствах. Для полного доступа: /subscribe")
                return
        if user_text.strip() == "/start":'''
text = text.replace(old_start_check, new_start_check)

# 3. Добавляем подписку в стартовое приветствие
old_start_commands = '"/inventory \\u2014 посмотреть аптечку\\n/reminders \\u2014 напоминания о приёме\\n"'
new_start_commands = '"/inventory \\u2014 посмотреть аптечку\\n/reminders \\u2014 напоминания о приёме\\n/subscribe \\u2014 оформить подписку\\n/status \\u2014 статус подписки\\n"'
text = text.replace(old_start_commands, new_start_commands)

# 4. Показываем статус подписки в /start
old_welcome_send = '            tg_send_with_menu(chat_id, welcome)'
new_welcome_send = '''            sub_info = get_subscription(uid)
            if sub_info["plan"] == "paid":
                welcome += "\\n\\n\\u2705 Подписка активна (%s дн.)" % sub_info["days_left"]
            elif sub_info["plan"] == "trial":
                welcome += "\\n\\n\\U0001f552 Пробный период (%s дн.). /subscribe для оплаты" % sub_info["days_left"]
            else:
                welcome += "\\n\\n\\U0001f512 Подписка неактивна. /subscribe для оплаты"
            tg_send_with_menu(chat_id, welcome)'''
text = text.replace(old_welcome_send, new_welcome_send)

with open('bot.py', 'w', encoding='utf-8') as f:
    f.write(text)
print('Done fix18!')