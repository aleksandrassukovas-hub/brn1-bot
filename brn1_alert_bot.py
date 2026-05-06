import os
import requests
import time
import re
from datetime import datetime, timedelta

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

POLL_INTERVAL = 30 
UTC_OFFSET = 3  
CASH_BALANCE = 100000  # Твой свободный кэш

# --- ТИКЕРЫ (СТРОГО ПО ТВОИМ СКРИНШОТАМ IBKR) ---
TICKERS = {
    "VWCE": "XETR:VWCE", 
    "SXR8": "XETR:SXR8", 
    "SXRV": "XETR:SXRV",
    "IGLD": "XETR:IGLD", 
    "JGPI": "XETR:JGPI", 
    "QDVB": "XETR:QDVB",
    "EIMI": "LSE:EIMI",   # USD
    "BRNT": "ICEEUR:BRN1!", # Фьючерс из твоего скрина
    "BTIC": "XETR:BTIC",
    "XEON": "XETR:XEON"
}

target_weights = {
    "VWCE": 30.0, "SXR8": 20.0, "SXRV": 10.0,
    "IGLD": 10.0, "JGPI": 10.0, "EIMI": 7.0,
    "QDVB": 5.0,  "BRNT": 5.0,  "BTIC": 3.0
}

# --- ТЕКУЩИЕ ПОЗИЦИИ (ИЗ ТВОЕГО СКРИНА IBKR) ---
CURRENT_POSITIONS = {
    "VWCE": 4.0, "SXR8": 1.0, "SXRV": 0.2, "IGLD": 3.0, "JGPI": 1000.0,
    "QDVB": 70.0, "EIMI": 5.0, "BRNT": 20.0, "BTIC": 8.0, "XEON": 70.0
}

last_update_id = -1 

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, data=payload, timeout=10)
        return r.status_code == 200
    except: return False

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
    """Расчет ребалансировки с учетом кэша и текущих позиций"""
    prices = {item["s"]: item["d"][0] for item in data}
    
    # 1. Считаем общую стоимость портфеля
    total_assets_value = 0
    for name, f_ticker in TICKERS.items():
        price = prices.get(f_ticker, 0)
        total_assets_value += price * CURRENT_POSITIONS.get(name, 0)
    
    total_portfolio = total_assets_value + CASH_BALANCE
    
    report = "🌙 *ОТЧЕТ И РЕБАЛАНСИРОВКА*\n"
    report += f"💰 Общий капитал: *{total_portfolio:,.2f}*\n"
    report += f"💵 Доступный кэш: *{CASH_BALANCE:,.2f}*\n\n"

    for name, f_ticker in TICKERS.items():
        if f_ticker not in prices: continue
        
        price = prices[f_ticker]
        cur_qty = CURRENT_POSITIONS.get(name, 0)
        cur_val = cur_qty * price
        cur_pct = (cur_val / total_portfolio) * 100
        
        target_pct = target_weights.get(name, 0)
        target_val = total_portfolio * (target_pct / 100)
        diff = target_val - cur_val
        
        # Формируем совет
        if diff > price:
            advice = f"🛒 *КУПИТЬ:* `{diff/price:.1f}` шт. (~{diff:,.0f})"
        elif diff < -price:
            advice = f"⚖️ *ПРОДАТЬ:* `{abs(diff)/price:.1f}` шт. (~{abs(diff):,.0f})"
        else:
            advice = "✅ В норме"
            
        report += f"*{name}*: {cur_pct:.1f}% -> цель {target_pct}%\n└ {advice}\n\n"
    
    return report

def handle_commands(data):
    global last_update_id, CASH_BALANCE, CURRENT_POSITIONS
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"timeout": 1, "offset": last_update_id + 1}
    
    try:
        r = requests.get(url, params=params, timeout=10)
        updates = r.json().get("result", [])
        for update in updates:
            last_update_id = update["update_id"]
            if "message" not in update or "text" not in update["message"]: continue
            msg = update["message"]
            text = msg["text"].strip()

            if text == "/status":
                send_telegram(f"📊 Текущий кэш: {CASH_BALANCE}\nВсего позиций: {len(CURRENT_POSITIONS)}")
            
            elif text == "/report":
                send_telegram(generate_analytical_report(data))

            # Команда обновления кэша: /cash 105000
            elif text.startswith("/cash"):
                try:
                    CASH_BALANCE = float(text.split()[1])
                    send_telegram(f"✅ Кэш обновлен: {CASH_BALANCE:,.2f}")
                except: send_telegram("❌ Формат: /cash 100000")

            # Команда обновления позиций: /pos VWCE 10
            elif text.startswith("/pos"):
                try:
                    parts = text.split()
                    t, q = parts[1].upper(), float(parts[2])
                    if t in TICKERS or t == "XEON":
                        CURRENT_POSITIONS[t] = q
                        send_telegram(f"✅ {t} обновлен: {q} шт.")
                except: send_telegram("❌ Формат: /pos VWCE 10")

    except Exception as e:
        print(f"Ошибка команд: {e}")

if __name__ == "__main__":
    print("🚀 Бот запущен (Версия 4.0 с кэшем)")
    requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates", params={"offset": -1})
    send_telegram("🤖 *Система управления капиталом активна*\n\n/report — план покупок\n/cash [число] — обновить кэш\n/pos [ТИКЕР] [кол-во] — обновить позицию")
    
    while True:
        try:
            m_data = get_market_data()
            if m_data:
                handle_commands(m_data)
            time.sleep(POLL_INTERVAL)
        except Exception as e:
            print(f"Loop error: {e}")
            time.sleep(10)
