import os
import requests
import time
import datetime

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
POLL_INTERVAL = 5 # Частота проверки команд в секундах

# Твой кэш
CASH_BALANCE = 100000 

# Тикеры
TICKERS = {
    "VWCE": "XETR:VWCE", 
    "SXR8": "XETR:SXR8", 
    "SXRV": "XETR:SXRV",
    "IGLD": "XETR:IGLD", 
    "JGPI": "XETR:JGPI", 
    "QDVB": "XETR:QDVB",
    "EIMI": "LSE:EIMI",   
    "BRNT": "ICEEUR:BRN1!", 
    "BTIC": "XETR:BTIC",
    "XEON": "XETR:XEON"
}

target_weights = {
    "VWCE": 30.0, "SXR8": 20.0, "SXRV": 10.0,
    "IGLD": 10.0, "JGPI": 10.0, "EIMI": 7.0,
    "QDVB": 5.0,  "BRNT": 5.0,  "BTIC": 3.0
}

CURRENT_POSITIONS = {
    "VWCE": 4.0, "SXR8": 1.0, "SXRV": 0.2, "IGLD": 3.0, "JGPI": 1000.0,
    "QDVB": 70.0, "EIMI": 5.0, "BRNT": 20.0, "BTIC": 8.0, "XEON": 70.0
}

last_update_id = -1 

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=payload, timeout=10)
    except: pass

def get_market_data():
    url = "https://scanner.tradingview.com/global/scan"
    payload = {
        "symbols": {"tickers": list(TICKERS.values())},
        "columns": ["close", "change", "RSI"]
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.json().get("data", [])
    except: return []

def generate_analytical_report(data):
    prices = {item["s"]: item["d"][0] for item in data}
    changes = {item["s"]: item["d"][1] for item in data}
    rsis = {item["s"]: item["d"][2] for item in data}
    
    total_assets_value = sum(prices.get(TICKERS[name], 0) * qty for name, qty in CURRENT_POSITIONS.items())
    total_portfolio = total_assets_value + CASH_BALANCE
    
    report = "🌙 *АНАЛИТИЧЕСКАЯ СВОДКА*\n"
    report += f"💰 Общий капитал: `{total_portfolio:,.2f}`\n"
    report += f"💵 Доступный кэш: `{CASH_BALANCE:,.2f}`\n"
    report += "---" * 4 + "\n\n"

    for name, f_ticker in TICKERS.items():
        if f_ticker not in prices: continue
        p, c, r = prices[f_ticker], changes[f_ticker], rsis[f_ticker]
        
        signal = "🔴 ПРОДАВАТЬ" if r > 70 else "🟢 ПОКУПАТЬ" if r < 30 else "⚪️ ДЕРЖАТЬ"
        cur_val = p * CURRENT_POSITIONS.get(name, 0)
        cur_pct = (cur_val / total_portfolio) * 100
        target_pct = target_weights.get(name, 0)
        diff = (total_portfolio * (target_pct / 100)) - cur_val
        
        report += f"*{name}*: `{p:.2f} ({c:+.2f}%)`\n"
        report += f"└ {signal} (RSI: {r:.1f})\n"
        report += f"└ Доля: {cur_pct:.1f}% -> Цель: {target_pct}%\n"
        
        if diff > p: report += f"└ 🛒 *КУПИТЬ:* `{diff/p:.1f}` шт. (~{diff:,.0f})\n\n"
        elif diff < -p: report += f"└ ⚖️ *ПРОДАТЬ:* `{abs(diff)/p:.1f}` шт. (~{abs(diff):,.0f})\n\n"
        else: report += "└ ✅ В норме\n\n"
    return report

def check_alerts():
    """Проверка резких движений и RSI"""
    data = get_market_data()
    alerts = []
    for item in data:
        f_ticker, p, c, r = item["s"], item["d"][0], item["d"][1], item["d"][2]
        name = next((k for k, v in TICKERS.items() if v == f_ticker), f_ticker)
        
        if r > 75: alerts.append(f"⚠️ *{name}* перегрет (RSI: {r:.1f})")
        elif r < 25: alerts.append(f"🔥 *{name}* перепродан (RSI: {r:.1f})")
        if abs(c) > 4.0: alerts.append(f"📊 Резкое движение {name}: {c:+.2f}%")
    
    if alerts:
        send_telegram("🔔 **ЕЖЕЧАСНОЕ УВЕДОМЛЕНИЕ**\n\n" + "\n".join(alerts))

def handle_commands():
    global last_update_id, CASH_BALANCE
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"offset": last_update_id + 1, "timeout": 1}
    try:
        r = requests.get(url, params=params, timeout=5).json()
        for update in r.get("result", []):
            last_update_id = update["update_id"]
            msg = update.get("message", {})
            text = msg.get("text", "")
            
            if text == "/report":
                send_telegram(generate_analytical_report(get_market_data()))
            elif text.startswith("/cash"):
                CASH_BALANCE = float(text.split()[1])
                send_telegram(f"✅ Кэш: {CASH_BALANCE:,.2f}")
            elif text.startswith("/pos"):
                parts = text.split()
                CURRENT_POSITIONS[parts[1].upper()] = float(parts[2])
                send_telegram(f"✅ {parts[1].upper()} обновлен")
    except: pass

if __name__ == "__main__":
    requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates", params={"offset": -1})
    send_telegram("🤖 **Бот-аналитик активен**\n/report — отчет\nАвто-мониторинг: 10:00-21:00")
    
    last_hour = -1
    while True:
        handle_commands()
        # Проверка алертов раз в час (МСК время в Railway обычно UTC, 7-18 это 10-21 МСК)
        now = datetime.datetime.now()
        if now.hour != last_hour and 7 <= now.hour <= 18:
            check_alerts()
            last_hour = now.hour
        time.sleep(POLL_INTERVAL)
