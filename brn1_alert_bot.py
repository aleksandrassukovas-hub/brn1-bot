import requests
import json
import time

def send_telegram(text: str) -> None:
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={
                "chat_id": CHAT_ID,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"send_telegram error: {e}")


def format_ticker_details(sym, full_name, p, chg, rsi):
    L = []
# ─────────────────────────────────────────
#  КОМАНДЫ
# ─────────────────────────────────────────
def handle_commands() -> None:
    global last_update_id, CASH_BALANCE

    if not BOT_TOKEN:
        return
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
            params={"offset": last_update_id + 1, "timeout": 1},
            timeout=5
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"getUpdates error: {e}")
        return

    for update in resp.json().get("result", []):
        last_update_id = update.get("update_id", last_update_id)
        msg  = update.get("message", {})

        if str(msg.get("chat", {}).get("id", "")) != str(CHAT_ID):
            continue

        text = (msg.get("text") or "").strip()

        if text == "/help":
            send_telegram(
                "*📖 Команды бота*\n\n"
                "/report — вечерняя сводка\n"
                "/morning — утренняя сводка\n"
                "/rebalance — план ребалансировки\n"
                "/news — новости рынка\n"
                "/alerts — проверить алерты\n"
                "/snapshot — сохранить позиции\n"
                "/pos TICKER N — обновить позицию\n"
                "/cash СУММА — обновить кэш\n"
                "/debug TICKER — детали по тикеру\n"
                "/help — эта справка"
            )

        elif text == "/report":
            send_telegram("⏳ Собираю данные...")
            send_telegram(generate_evening_report())

        elif text == "/morning":
            send_telegram("⏳ Готовлю утреннюю сводку...")
            send_telegram(generate_morning_report())

        elif text == "/rebalance":
            send_telegram("⏳ Считаю ребалансировку...")
            send_telegram(generate_rebalance_report())

        elif text == "/news":
            send_telegram("⏳ Загружаю новости...")
            lines = get_news_lines(5)
            if lines:
                send_telegram("*📰 Новости рынка*\n\n" + "\n\n".join(lines))
            else:
                send_telegram("⚠️ Новости недоступны. Проверь FINNHUB\\_TOKEN.")

        elif text == "/alerts":
            check_alerts()

        elif text == "/snapshot":
            snapshot = json.dumps({"cash": CASH_BALANCE, "positions": CURRENT_POSITIONS})
            send_telegram(
                "*💾 Сохрани в Railway Variables как POSITIONS\\_JSON:*\n\n"
                f"`{snapshot}`"
            )

        elif text.startswith("/cash"):
            parts = text.split()
            if len(parts) != 2:
                send_telegram("⚠️ Формат: /cash 50000")
                continue
            try:
                CASH_BALANCE = float(parts[1])
                send_telegram(f"✅ Кэш: *{CASH_BALANCE:,.0f} €*\nНапиши /snapshot чтобы сохранить.")
            except ValueError:
                send_telegram("⚠️ Сумма должна быть числом.")

        elif text.startswith("/pos"):
            parts = text.split()
            if len(parts) != 3:
                send_telegram("⚠️ Формат: /pos VWCE 10")
                continue
            symbol = parts[1].upper()
            try:
                qty = float(parts[2])
                CURRENT_POSITIONS[symbol] = qty
                send_telegram(f"✅ {symbol}: *{qty}* шт.\nНапиши /snapshot чтобы сохранить.")
            except ValueError:
                send_telegram("⚠️ Количество должно быть числом.")

        elif text.startswith("/debug"):
            parts = text.split()
            if len(parts) != 2:
                send_telegram("⚠️ Формат: /debug VWCE")
                continue
            send_telegram(_debug(parts[1]))

        else:
            if text.startswith("/"):
                send_telegram("❓ Неизвестная команда. Напиши /help")

# ─────────────────────────────────────────
#  MAIN LOOP
# ─────────────────────────────────────────
if __name__ == "__main__":
    send_telegram(
        "*🤖 Бот запущен*\n\n"
        "🗓 Авто-режим: только по будням (Пн–Пт)\n"
        "🌅 Утренняя сводка: 09:00 МСК\n"
        "🌙 Вечерняя сводка: 18:00 МСК\n"
        f"🔔 Алерты: {ALERT_SCHEDULE} МСК\n\n"
        "Команды (/report, /morning и т.д.) работают всегда.\n"
        "Напиши /help для списка команд."
    )

    last_alert_slot = None
    morning_sent    = False
    evening_sent    = False

    while True:
        # Команды обрабатываются всегда — независимо от дня и часа
        handle_commands()

        now  = now_msk()
        hour = now.hour

        # Автоматические сводки и алерты — только в рабочие дни
        if is_working_day(now):
            if hour == MORNING_HOUR and not morning_sent:
                send_telegram("⏳ Готовлю утреннюю сводку...")
                send_telegram(generate_morning_report())
                morning_sent = True
            elif hour != MORNING_HOUR:
                morning_sent = False

            if hour == EVENING_HOUR and not evening_sent:
                send_telegram("⏳ Готовлю вечернюю сводку...")
                send_telegram(generate_evening_report())
                evening_sent = True
            elif hour != EVENING_HOUR:
                evening_sent = False

            # Плановые алерты: 12:00, 15:00, 18:00 МСК
            alert_slot = (now.date(), hour)
            if hour in ALERT_HOURS and last_alert_slot != alert_slot:
                check_alerts()
                last_alert_slot = alert_slot
        else:
            # Выходной — сбрасываем флаги, чтобы в понедельник всё сработало штатно
            morning_sent    = False
            evening_sent    = False
            last_alert_slot = None

        time.sleep(POLL_INTERVAL)
