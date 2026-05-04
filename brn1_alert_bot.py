import os
import requests
import time

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

POLL_INTERVAL = 60 
# Порог волатильности по умолчанию (в %)
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
manual_levels = {ticker: {} for ticker in TICKERS} # {ticker: {price: triggered_bool}}
last_update_id = None

def get_market_data():
    url = "https://scanner.tradingview.com/global/scan"
    # Добавляем технические индикаторы для команды /info
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

def handle_commands(data):
    global last_update_id, threshold, manual_levels
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
                help_text = (
                    "📋 *Доступные команды:*\n\n"
                    "📈 *Просмотр:*\n"
                    " /status — цены всех активов\n"
                    " /info [тикер] — детали и RSI (напр. `/info SXR8`)\n\n"
                    "🔔 *Уровни (Alerts):*\n"
                    " /add [тикер] [цена] — поставить уведомление\n"
                    " /levels — список ваших уровней\n"
                    " /clear — удалить все уровни\n\n"
                    "⚙️ *Настройки:*\n"
                    " /threshold [число] — порог авто-уведомлений (сейчас: {0}%)\n"
                    " /help — этот список"
                ).format(threshold)
                send_telegram(help_text)

            elif cmd == "/status":
                report = "📊 *Котировки:*\n\n"
                found = {item["s"]: item["d"] for item in data}
                for s_name, f_ticker in TICKERS.items():
                    if f_ticker in found:
                        p, c = found[f_ticker][0], found[f_ticker][1]
                        report += f"{'🟢' if c >= 0 else '🔴'} `{s_name:5}`: *{p:.2f}* ({c:+.2f}%)\n"
                send_telegram(report)

            elif cmd == "/info" and len(parts) > 1:
                t = parts[1].upper()
                if t in TICKERS:
                    f_ticker = TICKERS[t]
                    d = next((item["d"] for item in data if item["s"] == f_ticker), None)
                    if d:
                        # Индексы: 0-price, 1-change, 2-RSI, 3-vol, 4-avg_vol
                        msg = (f"🔍 *Анализ {t}:*\n"
                               f"• Цена: `{d[0]:.2f}`\n"
                               f"• Изменение: {d[1]:+.2f}%\n"
                               f"• RSI (14): {d[2]:.1f} {'⚠️' if d[2]>70 or d[2]<30 else ''}\n"
                               f"• Объем: {int(d[3])} (ср. {int(d[4])})")
                        send_telegram(msg)
                else: send_telegram("❌ Тикер не найден")

            elif cmd == "/add" and len(parts) == 3:
                t, p = parts[1].upper(), parts[2]
                if t in TICKERS:
                    manual_levels[t][float(p)] = False
                    send_telegram(f"✅ Оповещение для {t} на `{p}` установлено")

            elif cmd == "/threshold" and len(parts) > 1:
                threshold = float(parts[1])
                send_telegram(f"⚙️ Порог волатильности: {threshold}%")

    except Exception as e: print(f"Cmd Error: {e}")

def check_logic(data):
    global last_notified_change
    for item in data:
        f_ticker = item["s"]
        short_name = next((k for k, v in TICKERS.items() if v == f_ticker), None)
        if not short_name: continue
        
        price, change_pct = item["d"][0], item["d"][1]

        # 1. Авто-волатильность
        if abs(change_pct) >= threshold:
            if abs(change_pct - last_notified_change[short_name]) >= 0.5:
                send_telegram(f"{'🚀' if change_pct > 0 else '⚠️'} *{short_name}* {change_pct:+.2f}%\nЦена: `{price:.2f}`")
                last_notified_change[short_name] = change_pct

        # 2. Ручные уровни
        for lvl, triggered in manual_levels[short_name].items():
            if not triggered and abs(price - lvl) <= (lvl * 0.0005):
                manual_levels[short_name][lvl] = True
                send_telegram(f"🎯 *{short_name}* достиг уровня `{lvl}`!")

# --- MAIN ---
while True:
    try:
        m_data = get_market_data()
        if m_data:
            check_logic(m_data)
            handle_commands(m_data)
        time.sleep(POLL_INTERVAL)
    except Exception as e:
        time.sleep(10)
