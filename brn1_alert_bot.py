import os
import requests
import time

# --- Настройки ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

POLL_INTERVAL = 60 
# Порог уведомления: если цена изменилась более чем на 2% от цены открытия дня
VOLATILITY_THRESHOLD = 2.0 

TICKERS = {
    "BRNT": "XETR:BRNT",
    "SXR8": "GETTEX:SXR8",
    "VWCE": "XETR:VWCE",
    "EIMI": "XETR:EIMI",
    "IGLD": "XETR:IGLD",
    "JGPI": "XETR:JGPI",
    "QDVB": "XETR:QDVB"
}

# Словарь для хранения последних цен, чтобы не спамить
last_notified_change = {ticker: 0 for ticker in TICKERS}

def get_market_data():
    url = "https://scanner.tradingview.com/global/scan"
    payload = {
        "symbols": {"tickers": list(TICKERS.values())},
        "columns": ["close", "change"] # change - это изменение в % за день от TV
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.json()["data"]
    except Exception as e:
        print(f"Ошибка данных: {e}")
        return None

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"})

def check_market():
    global last_notified_change
    data = get_market_data()
    if not data: return

    for item in data:
        tv_ticker = item["s"]
        price = item["d"][0]
        change_pct = item["d"][1] # Текущее изменение за день в %
        
        short_name = next(k for k, v in TICKERS.items() if v == tv_ticker)

        # 1. ПРОВЕРКА ВОЛАТИЛЬНОСТИ
        # Сравниваем текущее изменение с порогом (например, 2%)
        # Мы также проверяем, не уведомляли ли мы уже об этом (чтобы не писать каждую минуту)
        if abs(change_pct) >= VOLATILITY_THRESHOLD:
            # Если изменение стало значительно больше (на 0.5% выше), чем при прошлом уведомлении
            if abs(change_pct - last_notified_change[short_name]) >= 0.5:
                direction = "🚀 Резкий рост" if change_pct > 0 else "⚠️ Резкое падение"
                msg = (f"{direction} *{short_name}*!\n"
                       f"Изменение за день: *{change_pct:+.2f}%*\n"
                       f"Текущая цена: `{price}`")
                send_telegram(msg)
                last_notified_change[short_name] = change_pct

def handle_commands():
    # (Сюда вставляешь логику из прошлых ответов для /status и /add)
    pass

print("Автоматический монитор запущен...")
while True:
    try:
        check_market()
        # Тут же вызываем getUpdates для обработки команд, как в прошлом коде
        time.sleep(POLL_INTERVAL)
    except Exception as e:
        print(f"Ошибка: {e}")
        time.sleep(10)