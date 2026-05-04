import os
import requests
import time
from datetime import datetime, timedelta

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

POLL_INTERVAL = 60 
DEFAULT_VOLATILITY = 2.0 
UTC_OFFSET = 3  # Укажите ваш часовой пояс (напр. +3 для Москвы/Киева/Вильнюса)

# --- АКТИВЫ И ПРОФЕССИОНАЛЬНЫЕ ДОЛИ ---
TICKERS = {
    "VWCE": "XETR:VWCE",   # Мировой рынок
    "SXR8": "XETR:SXR8",   # S&P 500
    "SXRV": "XETR:SXRV",   # Nasdaq 100
    "IGLD": "XETR:IGLD",   # Золото
    "JGPI": "XETR:JGPI",   # Дивидендный доход
    "QDVB": "XETR:QDVB",   # Облигации
    "EIMI": "XETR:EIMI",   # Развивающиеся рынки
    "BRNT": "XETR:BRNT",   # Нефть
    "BTIC": "XETR:BTIC"    # Биткоин
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
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"Ошибка отправки в TG: {e}")

def send_daily_summary(data):
    """Генерация вечернего аналитического отчета"""
    report = "🌙 *ВЕЧЕРНИЙ ОТЧЕТ И АНАЛИТИКА*\n\n"
    
    for item in data:
        f_ticker = item["s"]
        s_name = next((k for k, v in TICKERS.items() if v == f_ticker), None)
        # d[0]:price, d[1]:change, d[2]:RSI
        price, change, rsi = item["d"][0], item["d"][1], item["d"][2]
        
        # Логика рекомендаций на основе RSI
        advice = "Держать"
        if rsi < 35: advice = "🛒 НЕДООЦЕНЕН (Покупать)"
        elif rsi > 65: advice = "💰 ПЕРЕГРЕТ (Фиксировать)"
        
        weight = target_weights.get(s_name, 0)
        report += f"*{s_name}*: `{price:.2f}` ({change:+.2f}%)\n└ {advice} | Цель: {weight}%\n\n"
    
    report += "💡 _Совет: Если доля актива отклонилась на 5% от цели, проведите ребалансировку._"
    send_telegram(report)

def handle_commands(data):
    global last_update_id, threshold, target_weights
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"timeout": 1, "offset": last_update_id + 1 if last_update_id else None}
    
    try:
        r = requests.get(url, params=params, timeout=5)
        updates = r.json().get("result", [])
        
        for update in updates:
            last_update_id = update["update_id"]
            if "message" not in update or "text" not in update["message"]: continue
            
            msg_text = update["message"]["text"].strip()
            parts = msg_text.split()
            if not parts: continue
            
            cmd = parts[0].lower().split('@')[0]

            if cmd == "/help":
                send_telegram(
                    "📋 *Команды ассистента:*\n"
                    "/status — текущие цены всех активов\n"
                    "/weights — целевые доли портфеля\n"
                    "/info [тикер] — детальный RSI и объем\n"
                    "/threshold [число] — порог уведомлений\n"
                    "/set_weight [тикер] [число] — изменить долю"
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
                w_report = "⚖️ *Целевое распределение:*\n\n"
                for t, w in target_weights.items():
                    if w > 0: w_report += f"• `{t:5}`: {w}%\n"
                w_report += f"\nСумма: {sum(target_weights.values())}%"
                send_telegram(w_report)

            elif cmd == "/info" and len(parts) > 1:
                t = parts[1].upper()
                if t in TICKERS:
                    f_t = TICKERS[t]
                    d = next((i["d"] for i in data if i["s"] == f_t), None)
                    if d:
                        msg = (f"🔍 *Анализ {t}:*\n• Цена: `{d[0]:.2f}`\n"
                               f"• RSI: {d[2]:.1f}\n• Объем: {int(d[3])}")
                        send_telegram(msg)
                else: send_telegram("❌ Тикер не найден")

            elif cmd == "/set_weight" and len(parts) == 3:
                t, w = parts[1].upper(), parts[2]
                if t in TICKERS:
                    target_weights[t] = float(w)
                    send_telegram(f"✅ Доля {t} изменена на {w}%")

            elif cmd == "/threshold" and len(parts) > 1:
                threshold = float(parts[1])
                send_telegram(f"⚙️ Порог уведомлений: {threshold}%")

    except Exception as e:
        print(f"Ошибка команд: {e}")

def check_logic(data):
    global last_notified_change, last_daily_report_day
    
    # 1. Мониторинг волатильности
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

    # 2. Таймер отчета (с учетом UTC)
    now_utc = datetime.utcnow()
    now_local = now_utc + timedelta(hours=UTC_OFFSET)
    
    if now_local.hour == 18 and now_local.minute == 0 and last_daily_report_day != now_local.day:
        send_daily_summary(data)
        last_daily_report_day = now_local.day

# --- ОСНОВНОЙ ЦИКЛ ---
print("Бот запущен...")
while True:
    try:
        m_data = get_market_data()
        if m_data:
            check_logic(m_data)
            handle_commands(m_data)
        time.sleep(POLL_INTERVAL)
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        time.sleep(10)
