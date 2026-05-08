import os
import requests
import time
import datetime

# --- КОНФИГУРАЦИЯ ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
POLL_INTERVAL = 5 

CASH_BALANCE = 100000 

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

VIX_TICKER = "TVC:VIX"

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
    if not BOT_TOKEN or not CHAT_ID: return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as e:
        print(f"Ошибка отправки: {e}")

def get_market_data():
    all_symbols = list(TICKERS.values()) + [VIX_TICKER]
    url = "https://scanner.tradingview.com/global/scan"
    payload = {
        "symbols": {"tickers": all_symbols},
        "columns": ["close", "change", "RSI"]
    }
    try:
        r = requests.post(url, json=payload, timeout=15)
        r.raise_for_status()
        return r.json().get("data", [])
    except Exception as e:
        print(f"Ошибка получения данных: {e}")
        return []

def generate_analytical_report(data):
    if not data: return "❌ Ошибка: Данные не получены."
    
    prices = {item["s"]: item["d"][0] for item in data}
    changes = {item["s"]: item["d"][1] for item in data}
    rsis = {item["s"]: item["d"][2] for item in data}
    
    vix_val = prices.get(VIX_TICKER, 0)
    vix_s = "🟢 Спокойствие" if vix_val < 15 else "🟡 Тревога" if vix_val < 25 else "🔴 ПАНИКА"

    total_assets = sum(prices.get(TICKERS[name], 0) * qty for name, qty in CURRENT_POSITIONS.items() if TICKERS.get(name) in prices)
    total_portfolio = total_assets + CASH_BALANCE
    
    report = f"🌙 *ОТЧЕТ ПО ПОРТФЕЛЮ*\n"
    report += f"📊 VIX: `{vix_val:.2f}` ({vix_s})\n"
    report += f"💰 Капитал: `{total_portfolio:,.2f}`\n"
    report += "---" * 4 + "\n\n"

    for name, f_ticker in TICKERS.items():
        if f_ticker not in prices: continue
        p, c, r = prices[f_ticker], changes[f_ticker], rsis[f_ticker] or 50.0
        signal = "🔴 ПРОДАВАТЬ" if r > 70 else "🟢 ПОКУПАТЬ" if r < 30 else "⚪️ ДЕРЖАТЬ"
        
        cur_val = p * CURRENT_POSITIONS.get(name, 0)
        target_pct = target_weights.get(name, 0)
        diff = (total_portfolio * (target_pct / 100)) - cur_val
        
        report += f"*{name}*: `{p:.2f}` ({signal})\n"
        if diff > p: report += f"└ 🛒 Купить: `{diff/p:.1f}` шт.\n"
        elif diff < -p: report += f"└ ⚖️ Продать: `{abs(diff)/p:.1f}` шт.\n"
        report += "\n"
    return report

def check_alerts():
    """Ежечасная проверка цен и VIX"""
    data = get_market_data()
    if not data: return
    
    prices = {item["s"]: item["d"][0] for item in data}
    vix_val = prices.get(VIX_TICKER, 0)
    vix_s = "🟢" if vix_val < 15 else "🟡" if vix_val < 25 else "🔴"
    
    # Базовое сообщение часа с VIX
    message = f"🔔 **ЧАСОВОЙ МОНИТОРИНГ**\n📈 Индекс VIX: `{vix_val:.2f}` {vix_s}\n\n"
    
    alerts = []
    for item in data:
        f_ticker, p, c, r = item["s"], item["d"][0], item["d"][1], item["d"][2]
        if f_ticker == VIX_TICKER: continue # VIX уже обработан выше

        name = next((k for k, v in TICKERS.items() if v == f_ticker), f_ticker)
        if r and r > 75: alerts.append(f"⚠️ {name} перегрет (RSI: {r:.1f})")
        elif r and r < 25: alerts.append(f"🔥 {name} перепродан (RSI: {r:.1f})")
        if abs(c) > 4.0: alerts.append(f"📊 Резкое движение {name}: {c:+.2f}%")
    
    if alerts:
        message += "События:\n" + "\n".join(alerts)
    else:
        message += "На рынке без резких изменений."
        
    send_telegram(message)

def handle_commands():
    global last_update_id, CASH_BALANCE
    if not BOT_TOKEN: return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"offset": last_update_id + 1, "timeout": 1}
    try:
        resp = requests.get(url, params=params, timeout=5)
        if resp.status_code == 200:
            for update in resp.json().get("result", []):
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
                    send_telegram(f"✅ {parts[1].upper()} обновлена")
    except: pass

if __name__ == "__main__":
    print("Запуск бота...")
    send_telegram("🤖 **Бот активен.**\nМониторинг цен и VIX включен ежечасно (10:00-21:00 МСК)")
    last_hour = -1
    while True:
        handle_commands()
        now = datetime.datetime.now()
        # Проверка в начале каждого часа (7-18 UTC соответствует 10-21 МСК)
        if now.hour != last_hour and 7 <= now.hour <= 18:
            check_alerts()
            last_hour = now.hour
        time.sleep(POLL_INTERVAL)
