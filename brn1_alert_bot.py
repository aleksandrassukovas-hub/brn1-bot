import os
import requests
import time
from datetime import datetime

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

POLL_INTERVAL = 60 
DEFAULT_VOLATILITY = 2.0 

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

# Глобальные состояния
threshold = DEFAULT_VOLATILITY
last_notified_change = {ticker: 0 for ticker in TICKERS}
manual_levels = {ticker: {} for ticker in TICKERS}
# Хранение целевых долей (в процентах)
target_weights = {ticker: 0.0 for ticker in TICKERS}
last_daily_report_day = None
last_update_id = None

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

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=payload)
    except: pass

def send_daily_summary(data):
    """Генерация вечернего отчета в 18:00"""
    report = "🌙 *ВЕЧЕРНИЙ ОТЧЕТ И РЕБАЛАНСИРОВКА*\n\n"
    total_weight_check = sum(target_weights.values())
    
    for item in data:
        f_ticker = item["s"]
        s_name = next((k for k, v in TICKERS.items() if v == f_ticker), None)
        # d[0]:price, d[1]:change, d[2]:RSI
        d = item["d"]
        
        # 1. Анализ перекупленности/перепроданности
        status = "Держать"
        if d[2] < 30: status = "🛒 ПОКУПАТЬ (RSI низкий)"
        elif d[2] > 70: status = "💰 ПРОДАВАТЬ (RSI высокий)"
        
        # 2. Учет долей (если заданы)
        weight_info = ""
        if target_weights[s_name] > 0:
            weight_info = f" | Цель: {target_weights[s_name]}%"

        report += f"*{s_name}*: {d[0]:.2f} ({d[1]:+.2f}%) \n└ {status}{weight_info}\n\n"
    
    if total_weight_check != 100 and total_weight_check > 0:
        report += f"⚠️ *Внимание:* Сумма ваших долей = {total_weight_check}%, а не 100%.\n"
    
    report += "💡 _Совет: Если актив вырос намного сильнее остальных, его доля в портфеле увеличилась. Пора продать излишки и купить отставшие._"
    send_telegram(report)

def handle_commands(data):
    global last_update_id, threshold, target_weights
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"timeout": 1, "offset": last_update_id + 1 if last_update_id else None}
    
    try:
        r = requests.get(url, params=params)
        for update in r.json().get("result", []):
            last_update_id = update["update_id"]
            if "message" not in update or "text" not in update["message"]: continue
            
            msg = update["message"]["text"]
            parts = msg.split()
            cmd = parts[0].lower()

            if cmd == "/help":
                send_telegram(
                    "📋 *Команды:*\n"
                    "/status — текущие цены\n"
                    "/set_weight [тикер] [процент] — задать долю (напр. `/set_weight SXR8 40`)\n"
                    "/weights — посмотреть ваши цели\n"
                    "/threshold [число] — порог алертов"
                )

            elif cmd == "/set_weight" and len(parts) == 3:
                t, w = parts[1].upper(), parts[2]
                if t in TICKERS:
                    target_weights[t] = float(w)
                    send_telegram(f"✅ Для {t} установлена целевая доля {w}%")
                else:
                    send_telegram("❌ Тикер не найден")

            elif cmd == "/weights":
                msg = "⚖️ *Целевые доли портфеля:*\n\n"
                for t, w in target_weights.items():
                    if w > 0: msg += f"• {t}: {w}%\n"
                send_telegram(msg)

            elif cmd == "/status":
                report = "📊 *Котировки:*\n\n"
                found = {item["s"]: item["d"] for item in data}
                for s_name, f_ticker in TICKERS.items():
                    if f_ticker in found:
                        p, c = found[f_ticker][0], found[f_ticker][1]
                        report += f"{'🟢' if c >= 0 else '🔴'} `{s_name:5}`: *{p:.2f}* ({c:+.2f}%)\n"
                send_telegram(report)

    except: pass

def check_logic(data):
    global last_notified_change, last_daily_report_day
    
    # 1. Проверка волатильности
    for item in data:
        f_ticker = item["s"]
        s_name = next((k for k, v in TICKERS.items() if v == f_ticker), None)
        price, change_pct = item["d"][0], item["d"][1]
        if abs(change_pct) >= threshold:
            if abs(change_pct - last_notified_change[s_name]) >= 0.5:
                send_telegram(f"{'🚀' if change_pct > 0 else '⚠️'} *{s_name}* {change_pct:+.2f}%\nЦена: `{price:.2f}`")
                last_notified_change[s_name] = change_pct

    # 2. Ежедневный отчет в 18:00
    now = datetime.now()
    if now.hour == 18 and now.minute == 0 and last_daily_report_day != now.day:
        send_daily_summary(data)
        last_daily_report_day = now.day

# --- ЦИКЛ ---
while True:
    try:
        m_data = get_market_data()
        if m_data:
            check_logic(m_data)
            handle_commands(m_data)
        time.sleep(POLL_INTERVAL)
    except:
        time.sleep(10)
