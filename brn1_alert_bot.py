import os
import requests
import time
from datetime import datetime, timedelta

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

POLL_INTERVAL = 30 # Уменьшил интервал для более быстрой реакции
DEFAULT_VOLATILITY = 2.0 
UTC_OFFSET = 3  # Ваш часовой пояс (Вильнюс/Киев/МСК)

# --- АКТИВЫ И ПРОФЕССИОНАЛЬНЫЕ ДОЛИ ---
TICKERS = {
    "VWCE": "XETR:VWCE", "SXR8": "XETR:SXR8", "SXRV": "XETR:SXRV",
    "IGLD": "XETR:IGLD", "JGPI": "XETR:JGPI", "QDVB": "XETR:QDVB",
    "EIMI": "XETR:EIMI", "BRNT": "XETR:BRNT", "BTIC": "XETR:BTIC"
}

target_weights = {
    "VWCE": 30.0, "SXR8": 20.0, "SXRV": 10.0,
    "IGLD": 10.0, "JGPI": 10.0, "EIMI": 7.0,
    "QDVB": 5.0,  "BRNT": 5.0,  "BTIC": 3.0
}

# --- ГЛОБАЛЬНЫЕ СОСТОЯНИЯ ---
threshold = DEFAULT_VOLATILITY
last_notified_change = {ticker: 0 for ticker in TICKERS}
last_daily_report_day = None
last_update_id = -1 # Начинаем с -1 для сброса очереди

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, data=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"Ошибка отправки: {e}")
        return False

def get_market_data():
    url = "https://scanner.tradingview.com/global/scan"
    payload = {
        "symbols": {"tickers": list(TICKERS.values())},
        "columns": ["close", "change", "RSI", "volume", "average_volume_10d_calc"]
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.json().get("data", [])
    except Exception as e:
        print(f"Ошибка API TradingView: {e}")
        return []

def handle_commands(data):
    global last_update_id, threshold, target_weights
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    
    # Если это первый запуск, очищаем старые сообщения
    params = {"timeout": 1}
    if last_update_id != -1:
        params["offset"] = last_update_id + 1
    
    try:
        r = requests.get(url, params=params, timeout=10)
        updates = r.json().get("result", [])
        
        for update in updates:
            last_update_id = update["update_id"]
            if "message" not in update or "text" not in update["message"]:
                continue
            
            text = update["message"]["text"].strip()
            # Проверка, что пишет именно владелец (CHAT_ID)
            if str(update["message"]["chat"]["id"]) != str(CHAT_ID):
                continue

            parts = text.split()
            cmd = parts[0].lower().split('@')[0]

            if cmd == "/help":
                send_telegram(
                    "✅ *Бот активен!*\n\n"
                    "📈 /status — цены и изменения\n"
                    "⚖️ /weights — распределение портфеля\n"
                    "⚙️ /threshold [число] — порог алертов\n"
                    "🔍 /info [тикер] — RSI и объемы"
                )
            
            elif cmd == "/status":
                report = "📊 *Текущие котировки:*\n\n"
                found = {item["s"]: item["d"] for item in data}
                for s_name, f_ticker in TICKERS.items():
                    if f_ticker in found:
                        p, c = found[f_ticker][0], found[f_ticker][1]
                        report += f"{'🟢' if c >= 0 else '🔴'} `{s_name:5}`: *{p:.2f}* ({c:+.2f}%)\n"
                send_telegram(report)

            elif cmd == "/weights":
                w_report = "⚖️ *Целевые доли:*\n\n"
                for t, w in target_weights.items():
                    w_report += f"• `{t:5}`: {w}%\n"
                send_telegram(w_report)

    except Exception as e:
        print(f"Ошибка в обработчике команд: {e}")

def check_logic(data):
    global last_notified_change, last_daily_report_day
    
    # 1. Волатильность
    for item in data:
        f_ticker = item["s"]
        s_name = next((k for k, v in TICKERS.items() if v == f_ticker), None)
        if not s_name: continue
        price, change_pct = item["d"][0], item["d"][1]
        
        if abs(change_pct) >= threshold:
            if abs(change_pct - last_notified_change[s_name]) >= 0.5:
                emoji = "🚀" if change_pct > 0 else "⚠️"
                send_telegram(f"{emoji} *{s_name}* {change_pct:+.2f}%\nЦена: `{price:.2f}`")
                last_notified_change[s_name] = change_pct

    # 2. Вечерний отчет
    now = datetime.utcnow() + timedelta(hours=UTC_OFFSET)
    if now.hour == 18 and now.minute == 0 and last_daily_report_day != now.day:
        # Упрощенный вызов отчета
        report = "🌙 *Вечерний статус-чек*\n\n"
        for item in data:
            f_ticker = item["s"]
            s_name = next((k for k, v in TICKERS.items() if v == f_ticker), None)
            report += f"*{s_name}*: {item['d'][0]:.2f} ({item['d'][1]:+.2f}%)\n"
        send_telegram(report)
        last_daily_report_day = now.day

# --- ЗАПУСК ---
if __name__ == "__main__":
    print("🚀 Запуск ассистента...")
    # Делаем пробный запуск, чтобы бот сразу считал текущий ID обновлений
    get_market_data()
    # Первое сообщение при запуске для проверки связи
    send_telegram("🤖 Бот запущен и готов к работе. Напишите /help")
    
    while True:
        try:
            m_data = get_market_data()
            handle_commands(m_data)
            if m_data:
                check_logic(m_data)
            time.sleep(POLL_INTERVAL)
        except Exception as e:
            print(f"Ошибка цикла: {e}")
            time.sleep(10)
