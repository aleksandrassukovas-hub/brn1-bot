import os
import requests
import time

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

POLL_INTERVAL = 60 
VOLATILITY_THRESHOLD = 2.0  # Уведомлять при изменении > 2% за день

TICKERS = {
    "BRNT": "XETR:BRNT",
    "SXR8": "GETTEX:SXR8",
    "VWCE": "XETR:VWCE",
    "EIMI": "XETR:EIMI",
    "IGLD": "XETR:IGLD",
    "JGPI": "XETR:JGPI",
    "QDVB": "XETR:QDVB"
}

# Состояние для защиты от спама и хранения команд
last_notified_change = {ticker: 0 for ticker in TICKERS}
last_update_id = None

def get_market_data():
    """Запрос данных котировок из TradingView"""
    url = "https://scanner.tradingview.com/global/scan"
    payload = {
        "symbols": {"tickers": list(TICKERS.values())},
        "columns": ["close", "change"]
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.json().get("data", [])
    except Exception as e:
        print(f"Ошибка получения данных: {e}")
        return []

def send_telegram(text):
    """Отправка сообщения в Telegram"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"})
    except Exception as e:
        print(f"Ошибка сети TG: {e}")

def handle_commands(data):
    """Обработка входящих сообщений (команд)"""
    global last_update_id
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"timeout": 1, "offset": last_update_id + 1 if last_update_id else None}
    
    try:
        r = requests.get(url, params=params)
        updates = r.json().get("result", [])
        for update in updates:
            last_update_id = update["update_id"]
            if "message" in update and "text" in update["message"]:
                text = update["message"]["text"].lower()
                
                if text == "/status":
                    report = "📊 *Текущие котировки:*\n\n"
                    for item in data:
                        tv_ticker = item["s"]
                        short_name = next(k for k, v in TICKERS.items() if v == tv_ticker)
                        price = item["d"][0]
                        change = item["d"][1]
                        emoji = "🟢" if change >= 0 else "🔴"
                        report += f"{emoji} `{short_name:5}`: *{price:.2f}* ({change:+.2f}%)\n"
                    send_telegram(report)
                    
                elif text == "/start":
                    send_telegram("Бот запущен. Используй /status для проверки цен.")
    except Exception as e:
        print(f"Ошибка при получении обновлений: {e}")

def check_volatility(data):
    """Автоматическая проверка резких движений"""
    global last_notified_change
    for item in data:
        tv_ticker = item["s"]
        price = item["d"][0]
        change_pct = item["d"][1]
        short_name = next(k for k, v in TICKERS.items() if v == tv_ticker)

        # Если изменение выше порога и оно изменилось более чем на 0.5% с прошлого раза
        if abs(change_pct) >= VOLATILITY_THRESHOLD:
            if abs(change_pct - last_notified_change[short_name]) >= 0.5:
                direction = "🚀 Рост" if change_pct > 0 else "⚠️ Падение"
                msg = (f"{direction} *{short_name}* на {change_pct:+.2f}%\n"
                       f"Текущая цена: `{price:.2f}`")
                send_telegram(msg)
                last_notified_change[short_name] = change_pct

# --- ГЛАВНЫЙ ЦИКЛ ---
print("Ассистент запущен и готов к работе...")

while True:
    try:
        # 1. Получаем свежие данные
        market_data = get_market_data()
        
        if market_data:
            # 2. Проверяем, не нужно ли отправить алерт по волатильности
            check_volatility(market_data)
            
            # 3. Слушаем команды (передаем данные, чтобы /status ответил мгновенно)
            handle_commands(market_data)
            
        time.sleep(POLL_INTERVAL)
    except Exception as e:
        print(f"Ошибка в основном цикле: {e}")
        time.sleep(10)