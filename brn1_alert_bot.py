import os
import requests
import time

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
POLL_INTERVAL = 60 

# Твой кэш и целевые доли
CASH_BALANCE = 100000 

# Тикеры настроены строго под твои площадки в IBKR
TICKERS = {
    "VWCE": "XETR:VWCE", 
    "SXR8": "XETR:SXR8", 
    "SXRV": "XETR:SXRV",
    "IGLD": "XETR:IGLD", 
    "JGPI": "XETR:JGPI", 
    "QDVB": "XETR:QDVB",
    "EIMI": "LSE:EIMI",   
    "BRNT": "ICEEUR:BRN1!", # Фьючерс Brent
    "BTIC": "XETR:BTIC",
    "XEON": "XETR:XEON"
}

target_weights = {
    "VWCE": 30.0, "SXR8": 20.0, "SXRV": 10.0,
    "IGLD": 10.0, "JGPI": 10.0, "EIMI": 7.0,
    "QDVB": 5.0,  "BRNT": 5.0,  "BTIC": 3.0
}

# Текущие позиции из твоего скриншота IBKR
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
    
    # Расчет общей стоимости портфеля
    total_assets_value = 0
    for name, f_ticker in TICKERS.items():
        price = prices.get(f_ticker, 0)
        total_assets_value += price * CURRENT_POSITIONS.get(name, 0)
    
    total_portfolio = total_assets_value + CASH_BALANCE
    
    report = "🌙 *АНАЛИТИЧЕСКАЯ СВОДКА*\n"
    report += f"💰 Общий капитал: `{total_portfolio:,.2f}`\n"
    report += f"💵 Доступный кэш: `{CASH_BALANCE:,.2f}`\n"
    report += "---" * 4 + "\n\n"

    for name, f_ticker in TICKERS.items():
        if f_ticker not in prices or name not in target_weights: continue
        
        price = prices[f_ticker]
        change = changes[f_ticker]
        rsi = rsis[f_ticker]
        
        # Сигнал по RSI
        if rsi > 70: signal = "🔴 ПРОДАВАТЬ"
        elif rsi < 30: signal = "🟢 ПОКУПАТЬ"
        else: signal = "⚪️ ДЕРЖАТЬ"

        # Ребалансировка
        cur_val = price * CURRENT_POSITIONS.get(name, 0)
        cur_pct = (cur_val / total_portfolio) * 100
        target_pct = target_weights[name]
        target_val = total_portfolio * (target_pct / 100)
        diff = target_val - cur_val
        
        report += f"*{name}*: `{price:.2f} ({change:+.2f}%)`\n"
        report += f"└ {signal} (RSI: {rsi:.1f})\n"
        report += f"└ Доля: {cur_pct:.1f}% -> Цель: {target_pct}%\n"
        
        if diff > price:
            report += f"└ 🛒 *КУПИТЬ:* `{diff/price:.1f}` шт. (~{diff:,.0f})\n\n"
        elif diff < -price:
            report += f"└ ⚖️ *ПРОДАТЬ:* `{abs(diff)/price:.1f}` шт. (~{abs(diff):,.0f})\n\n"
        else:
            report += "└ ✅ В норме\n\n"
    
    return report

def handle_commands():
    global last_update_id, CASH_BALANCE
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"offset": last_update_id + 1, "timeout": 1}
    try:
        r = requests.get(url, params=params, timeout=10)
        updates = r.json().get("result", [])
        for update in updates:
            last_update_id = update["update_id"]
            if "message" not in update or "text" not in update["message"]: continue
            text = update["message"]["text"]
            
            if text == "/report":
                data = get_market_data()
                send_telegram(generate_analytical_report(data))
            elif text.startswith("/cash"):
                try:
                    CASH_BALANCE = float(text.split()[1])
                    send_telegram(f"✅ Кэш обновлен: {CASH_BALANCE:,.2f}")
                except: pass
            elif text.startswith("/pos"):
                try:
                    parts = text.split()
                    t, q = parts[1].upper(), float(parts[2])
                    CURRENT_POSITIONS[t] = q
                    send_telegram(f"✅ Позиция {t} обновлена: {q}")
                except: pass
    except: pass

if __name__ == "__main__":
    # Сброс старых обновлений
    requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates", params={"offset": -1})
    send_telegram("🤖 *Бот-аналитик запущен*\nИспользуй /report для отчета")
    
    while True:
        handle_commands()
        time.sleep(2)
