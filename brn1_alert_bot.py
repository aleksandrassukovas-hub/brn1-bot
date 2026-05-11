Diff
Logs

portfolio_bot.py
portfolio_bot.py
New
+296
-0

import os
import time
import datetime
import requests

# --- CONFIG ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
POLL_INTERVAL = 5

CASH_BALANCE = 100000.0

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
    "XEON": "XETR:XEON",
}

REV_TICKERS = {v: k for k, v in TICKERS.items()}
VIX_TICKER = "TVC:VIX"

TARGET_WEIGHTS = {
    "VWCE": 30.0,
    "SXR8": 20.0,
    "SXRV": 10.0,
    "IGLD": 10.0,
    "JGPI": 10.0,
    "EIMI": 7.0,
    "QDVB": 5.0,
    "BRNT": 5.0,
    "BTIC": 3.0,
}

CURRENT_POSITIONS = {
    "VWCE": 4.0,
    "SXR8": 1.0,
    "SXRV": 0.2,
    "IGLD": 3.0,
    "JGPI": 1000.0,
    "QDVB": 70.0,
    "EIMI": 5.0,
    "BRNT": 20.0,
    "BTIC": 8.0,
    "XEON": 70.0,
}

last_update_id = -1


def send_telegram(text: str) -> None:
    if not BOT_TOKEN or not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"}
    try:
        requests.post(url, data=payload, timeout=10)
    except Exception as exc:
        print(f"Ошибка отправки: {exc}")


def get_market_data() -> list[dict]:
    all_symbols = list(TICKERS.values()) + [VIX_TICKER]
    url = "https://scanner.tradingview.com/global/scan"
    payload = {"symbols": {"tickers": all_symbols}, "columns": ["close", "change", "RSI"]}
    try:
        response = requests.post(url, json=payload, timeout=15)
        response.raise_for_status()
        return response.json().get("data", [])
    except Exception as exc:
        print(f"Ошибка получения данных: {exc}")
        return []


def extract_maps(data: list[dict]) -> tuple[dict, dict, dict]:
    prices: dict[str, float] = {}
    changes: dict[str, float] = {}
    rsis: dict[str, float | None] = {}

    for item in data:
        symbol = item.get("s")
        values = item.get("d", [])
        if not symbol or len(values) < 3:
            continue
        prices[symbol] = values[0] if values[0] is not None else 0.0
        changes[symbol] = values[1] if values[1] is not None else 0.0
        rsis[symbol] = values[2]

    return prices, changes, rsis


def generate_analytical_report(data: list[dict]) -> str:
    if not data:
        return "❌ Ошибка: данные не получены."

    prices, changes, rsis = extract_maps(data)
    vix_val = prices.get(VIX_TICKER, 0.0)
    vix_state = "🟢 Спокойствие" if vix_val < 15 else "🟡 Тревога" if vix_val < 25 else "🔴 ПАНИКА"

    total_assets = sum(
        prices.get(TICKERS[name], 0.0) * qty
        for name, qty in CURRENT_POSITIONS.items()
        if TICKERS.get(name) in prices
    )
    total_portfolio = total_assets + CASH_BALANCE

    report = "🌙 *АНАЛИТИЧЕСКАЯ СВОДКА*\n"
    report += f"💰 Общий капитал: `{total_portfolio:,.2f}`\n"
    report += f"💵 Доступный кэш: `{CASH_BALANCE:,.2f}`\n"
    report += f"📊 Индекс VIX: `{vix_val:.2f}` ({vix_state})\n"
    report += "------------\n\n"

    for name, f_ticker in TICKERS.items():
        if f_ticker not in prices:
            continue

        price = prices[f_ticker]
        change = changes.get(f_ticker, 0.0)
        rsi = rsis.get(f_ticker)
        safe_rsi = 50.0 if rsi is None else rsi

        signal = "🔴 ПРОДАВАТЬ" if safe_rsi > 70 else "🟢 ПОКУПАТЬ" if safe_rsi < 30 else "⚪️ ДЕРЖАТЬ"

        current_value = price * CURRENT_POSITIONS.get(name, 0.0)
        target_pct = TARGET_WEIGHTS.get(name, 0.0)
        diff = (total_portfolio * (target_pct / 100)) - current_value

        report += f"*{name}*: `{price:.2f}` ({change:+.2f}%)\n"
        report += f"└ {signal} (RSI: {safe_rsi:.1f})\n"

        current_weight = (current_value / total_portfolio * 100) if total_portfolio > 0 else 0.0
        report += f"└ Доля: `{current_weight:.1f}%` -> Цель: `{target_pct:.1f}%`\n"

        if price > 0:
            if diff > price:
                report += f"└ 🛒 КУПИТЬ: `{diff / price:.1f}` шт.\n"
            elif diff < -price:
                report += f"└ ⚖️ ПРОДАТЬ: `{abs(diff) / price:.1f}` шт.\n"
        report += "\n"

    return report


def check_alerts() -> None:
    """Ежечасная проверка цен и VIX."""
    data = get_market_data()
    if not data:
        return

    prices, changes, rsis = extract_maps(data)
    vix_val = prices.get(VIX_TICKER, 0.0)
    vix_s = "🟢" if vix_val < 15 else "🟡" if vix_val < 25 else "🔴"

    message = f"🔔 **ЧАСОВОЙ МОНИТОРИНГ**\n📈 Индекс VIX: `{vix_val:.2f}` {vix_s}\n\n"

    alerts = []
    for symbol, price in prices.items():
        if symbol == VIX_TICKER:
            continue
        name = REV_TICKERS.get(symbol, symbol)
        change = changes.get(symbol, 0.0)
        rsi = rsis.get(symbol)

        if rsi is not None and rsi > 75:
            alerts.append(f"⚠️ {name} перегрет (RSI: {rsi:.1f})")
        elif rsi is not None and rsi < 25:
            alerts.append(f"🔥 {name} перепродан (RSI: {rsi:.1f})")

        if abs(change) > 4.0:
            alerts.append(f"📊 Резкое движение {name}: {change:+.2f}%")

    if alerts:
        message += "События:\n" + "\n".join(alerts)
    else:
        message += "На рынке без резких изменений."

    send_telegram(message)




def debug_symbol_report(symbol: str) -> str:
    data = get_market_data()
    if not data:
        return "❌ Ошибка: данные не получены."

    prices, changes, rsis = extract_maps(data)
    symbol = symbol.upper()

    if symbol == "VIX":
        tv_symbol = VIX_TICKER
        human_name = "VIX"
    else:
        tv_symbol = TICKERS.get(symbol)
        human_name = symbol

    if not tv_symbol:
        available = ", ".join(sorted(TICKERS.keys()))
        return f"⚠️ Неизвестный тикер `{symbol}`. Доступно: {available}, VIX"

    if tv_symbol not in prices:
        return f"⚠️ По тикеру `{human_name}` нет рыночных данных прямо сейчас."

    price = prices.get(tv_symbol, 0.0)
    change = changes.get(tv_symbol, 0.0)
    rsi = rsis.get(tv_symbol)
    rsi_txt = "n/a" if rsi is None else f"{rsi:.2f}"

    lines = [
        f"🐞 *DEBUG {human_name}*",
        f"Символ TV: `{tv_symbol}`",
        f"Цена: `{price:.4f}`",
        f"Изм. за день: `{change:+.2f}%`",
        f"RSI: `{rsi_txt}`",
    ]

    if human_name != "VIX":
        qty = CURRENT_POSITIONS.get(human_name, 0.0)
        position_value = qty * price
        lines.append(f"Позиция: `{qty}` шт. (~`{position_value:,.2f}`)")

    return "\n".join(lines)

def handle_commands() -> None:
    global last_update_id, CASH_BALANCE
    if not BOT_TOKEN:
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    params = {"offset": last_update_id + 1, "timeout": 1}

    try:
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        for update in resp.json().get("result", []):
            last_update_id = update.get("update_id", last_update_id)
            msg = update.get("message", {})
            text = (msg.get("text") or "").strip()

            if text == "/report":
                send_telegram(generate_analytical_report(get_market_data()))

            elif text.startswith("/cash"):
                parts = text.split()
                if len(parts) != 2:
                    send_telegram("⚠️ Формат: /cash <сумма>")
                    continue
                try:
                    CASH_BALANCE = float(parts[1])
                    send_telegram(f"✅ Кэш: {CASH_BALANCE:,.2f}")
                except ValueError:
                    send_telegram("⚠️ Ошибка: сумма должна быть числом.")

            elif text.startswith("/pos"):
                parts = text.split()
                if len(parts) != 3:
                    send_telegram("⚠️ Формат: /pos <TICKER> <кол-во>")
                    continue
                symbol = parts[1].upper()
                try:
                    quantity = float(parts[2])
                    CURRENT_POSITIONS[symbol] = quantity
                    send_telegram(f"✅ {symbol} обновлена: {quantity}")
                except ValueError:
                    send_telegram("⚠️ Ошибка: количество должно быть числом.")

            elif text.startswith("/debug"):
                parts = text.split()
                if len(parts) != 2:
                    send_telegram("⚠️ Формат: /debug <TICKER|VIX>")
                    continue
                send_telegram(debug_symbol_report(parts[1]))

    except Exception as exc:
        print(f"Ошибка handle_commands: {exc}")


if __name__ == "__main__":
    print("Запуск бота...")
    send_telegram("🤖 **Бот активен.**\nМониторинг цен и VIX включен ежечасно (10:00-21:00 МСК)")
    last_hour = -1

    while True:
        handle_commands()
        now_utc = datetime.datetime.now(datetime.timezone.utc)
        # 07:00-18:59 UTC соответствует 10:00-21:59 МСК
        if now_utc.hour != last_hour and 7 <= now_utc.hour <= 18:
            check_alerts()
            last_hour = now_utc.hour
        time.sleep(POLL_INTERVAL)
