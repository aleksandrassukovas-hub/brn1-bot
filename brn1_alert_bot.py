import os
import requests
import time

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]

POLL_INTERVAL_SECONDS = 10
TOUCH_TOLERANCE = 0.03

levels = {}
last_update_id = None


def get_price():
    url = "https://scanner.tradingview.com/futures/scan"
    payload = {
        "symbols": {"tickers": ["ICEEUR:BRN1!"], "query": {"types": []}},
        "columns": ["close"]
    }
    r = requests.post(url, json=payload)
    data = r.json()
    return data["data"][0]["d"][0]


def send_message(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": text})


def get_updates():
    global last_update_id
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"timeout": 1}
    if last_update_id:
        params["offset"] = last_update_id + 1

    r = requests.get(url, params=params)
    data = r.json()

    for update in data["result"]:
        last_update_id = update["update_id"]
        if "message" in update and "text" in update["message"]:
            handle_command(update["message"]["text"])


def handle_command(text):
    global levels

    parts = text.split()
    cmd = parts[0]

    if cmd == "/add":
        added = []
        for p in parts[1:]:
            try:
                val = float(p)
                levels[val] = False
                added.append(val)
            except:
                pass
        send_message(f"Добавлены уровни: {added}")

    elif cmd == "/remove":
        removed = []
        for p in parts[1:]:
            try:
                val = float(p)
                if val in levels:
                    del levels[val]
                    removed.append(val)
            except:
                pass
        send_message(f"Удалены: {removed}")

    elif cmd == "/levels":
        if not levels:
            send_message("Нет уровней")
            return

        text = "Уровни:\n"
        for lvl, triggered in levels.items():
            status = "✅" if triggered else "⏳"
            text += f"{lvl} {status}\n"

        send_message(text)

    elif cmd == "/clear":
        levels.clear()
        send_message("Все уровни удалены")

    elif cmd == "/status":
        price = get_price()
        text = f"Цена: {price}\n\n"
        for lvl, triggered in levels.items():
            status = "✅" if triggered else "⏳"
            text += f"{lvl} {status}\n"
        send_message(text)


def check_levels(price):
    for lvl in levels:
        if not levels[lvl]:
            if abs(price - lvl) <= TOUCH_TOLERANCE:
                levels[lvl] = True
                send_message(f"🎯 BRN1! коснулся уровня {lvl}\nЦена: {price}")


print("Бот запущен...")

while True:
    try:
        get_updates()
        price = get_price()
        check_levels(price)
        time.sleep(POLL_INTERVAL_SECONDS)
    except Exception as e:
        print("Ошибка:", e)
        time.sleep(5)