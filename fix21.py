with open('bot.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Находим весь блок проверки подписки и заменяем его целиком
# Ищем от "sub = get_subscription" до "if user_text.strip() == "/start":"

old_block = '''        sub = get_subscription(uid)
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
                return'''

new_block = '''        if uid == ADMIN_ID:
            sub = {"plan": "paid", "active": True, "trial": False, "days_left": 999}
        else:
            sub = get_subscription(uid)
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
        if not sub["active"]:
            is_free_query = any(w in user_text.lower() for w in ["что такое", "для чего", "от чего", "зачем", "описание", "инструкция", "побочные", "аналог"])
            if not is_free_query and user_text.strip() not in ["/start"]:
                if sub.get("trial"):
                    tg_send(chat_id, "\\u23f0 Пробный период закончился.\\n\\nВам доступны бесплатные справки о лекарствах. Для полного доступа оформите подписку: /subscribe")
                else:
                    tg_send(chat_id, "\\U0001f512 Эта функция доступна по подписке.\\n\\nВам доступны бесплатные справки о лекарствах. Для полного доступа: /subscribe")
                return'''

text = text.replace(old_block, new_block)

with open('bot.py', 'w', encoding='utf-8') as f:
    f.write(text)
print('Done fix21!')