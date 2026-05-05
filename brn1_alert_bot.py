import os
import requests
import time
from datetime import datetime, timedelta

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

POLL_INTERVAL = 30 
DEFAULT_VOLATILITY = 2.0 
UTC_OFFSET = 3  

# --- АКТИВЫ И ДОЛИ ---
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

# --- СОСТОЯНИЯ ---
threshold = DEFAULT_VOLATILITY
last_notified_change = {ticker: 0 for ticker in TICKERS}
last_daily_report_day = None
last_update_id = -1 

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
        print(f"Ошибка API: {e}")
        return []

def generate_analytical_report(data):
    """Генерация текста с аналитикой и рекомендациями"""
    report = "🌙 *АНАЛИТИЧЕСКАЯ СВОДКА*\n\n"
    for item in data:
        f_ticker = item["s"]
        s_name = next((k for k, v in TICKERS.items() if v == f_ticker), None)
        if not s_name: continue
        
        d = item["d"]
        price, change, rsi = d[0], d[1], d[2]
        
        # Рекомендация по RSI
        if rsi is not None:
            if rsi < 35: advice = "🟢 *ПОКУПАТЬ* (RSI low)"
            elif rsi > 65: advice = "🔴 *ПРОДАВАТЬ* (RSI high)"
            else: advice = "⚪️ ДЕРЖАТЬ"
        else:
            advice = "⚪️ Нет данных RSI"
            
        report += f"*{s_name}*: `{price:.2f}` ({change:+.2f}%)\n└ {advice} | Цель: {target_weights[s_name]}%\n\n"
    
    report += "💡 _Совет: Ребалансируйте, если отклонение > 5%._"
    return report

def handle_commands(data):
    global last_update_id, threshold
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    
    params = {"timeout": 1}
    if last_update_id != -1:
        params["offset"] = last_update_id + 1
    
    try:
        r = requests.get(url, params=params, timeout=10)
        updates = r.json().get("result", [])
        
        for update in updates:
            last_update_id = update["update_id"]
            if "message" not in update or "text" not in update["message"]: continue
            if str(update["message"]["chat"]["id"]) != str(CHAT_ID): continue

            text = update["message"]["text"].strip()
            parts = text.split()
            cmd = parts[0].lower().split('@')[0]

            if cmd == "/help":
                send_telegram("📈 /status — цены\n⚖️ /weights — доли\n🌙 /report — аналитика")
            
            elif cmd == "/status":
                report = "📊 *Котировки:*\n\n"
                found = {i["s"]: i["d"] for i in data}
                for sn, ft in TICKERS.items():
                    if ft in found:
                        report += f"{sn:5}: `{found[ft][0]:.2f}` ({found[ft][1]:+.2f}%)\n"
                send_telegram(report)

            elif cmd == "/weights":
                msg = "⚖️ *Целевые доли:*\n\n"
                for t, w in target_weights.items():
                    msg += f"• `{t:5}`: {w}%\n"
                send_telegram(msg)
            
            elif cmd == "/report":
                send_telegram(generate_analytical_report(data))

            elif cmd == "/threshold" and len(parts) > 1:
                threshold = float(parts[1])
                send_telegram(f"✅ Порог изменен на {threshold}%")

    except Exception as e:
        print(f"Ошибка команд: {e}")

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

    # 2. Вечерний отчет (18:00)
    now = datetime.utcnow() + timedelta(hours=UTC_OFFSET)
    if now.hour == 18 and now.minute == 0 and last_daily_report_day != now.day:
        send_telegram(generate_analytical_report(data))
        last_daily_report_day = now.day

# --- ЗАПУСК ---
if __name__ == "__main__":
    print("🚀 Запуск ассистента...")
    # Очистка старых сообщений перед стартом
    initial_r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates", params={"offset": -1})
    
    send_telegram("🤖 Бот запущен. Напишите /report для проверки.")
    
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
