import os
import requests
import time

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

POLL_INTERVAL = 60 
VOLATILITY_THRESHOLD = 2.0 

# Обновленный список с уточненными тикерами для европейских бирж
TICKERS = {
    "VWCE": "XETR:VWCE",
    "IGLD": "XETR:IGLD",
    "JGPI": "XETR:JGPI",
    "QDVB": "XETR:QDVB",
    "EIMI": "XETR:EIMI",
    "SXR8": "XETR:SXR8",
    "BRNT": "XETR:BRNT",
    "BTIC": "XETR:BTIC",
    "SXRV": "XETR:SXRV"
}

last_notified_change = {ticker: 0 for ticker in TICKERS}
last_update_id = None

def get_market_data():
    url = "https://scanner.tradingview.com/global/scan"
    payload = {
        "symbols": {"tickers": list(TICKERS.values())},
        "columns": ["close", "change"]
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        # Если глобальный сканер не нашел часть тикеров, 
        # данные могут прийти не в полном объеме
        return r.json().get("data", [])
    except Exception as e:
        print(f"Ошибка получения данных: {e}")
        return []

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"})
    except: pass

def handle_commands(data):
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
                    # Проходимся по нашему словарю, чтобы ничего не потерять
                    found_tickers = {item["s"]: item["d"] for item in data}
                    
                    for short_name, full_ticker in TICKERS.items():
                        if full_ticker in found_tickers:
                            price = found_tickers[full_ticker][0]
                            change = found_tickers[full_ticker][1]
                            emoji = "🟢" if change >= 0 else "🔴"
                            report += f"{emoji} `{short_name:5}`: *{price:.2f}* ({change:+.2f}%)\n"
                        else:
                            report += f"⚪️ `{short_name:5}`: _нет данных_\n"
                    
                    send_telegram(report)
    except: pass

def check_volatility(data):
    global last_notified_change
    for item in data:
        full_ticker = item["s"]
        # Ищем короткое имя
        short_name = next((k for k, v in TICKERS.items() if v == full_ticker), None)
        if not short_name: continue
        
        price = item["d"][0]
        change_pct = item["d"][1]

        if abs(change_pct) >= VOLATILITY_THRESHOLD:
            if abs(change_pct - last_notified_change[short_name]) >= 0.5:
                direction = "🚀 Рост" if change_pct > 0 else "⚠️ Падение"
                msg = f"{direction} *{short_name}* на {change_pct:+.2f}%\nЦена: `{price:.2f}`"
                send_telegram(msg)
                last_notified_change[short_name] = change_pct

# --- ЦИКЛ ---
while True:
    try:
        market_data = get_market_data()
        check_volatility(market_data)
        handle_commands(market_data)
        time.sleep(POLL_INTERVAL)
    except Exception as e:
        time.sleep(10)
