import os
import time
import json
import datetime
import requests
from typing import Dict, List, Optional, Tuple

# ─────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────
BOT_TOKEN      = os.environ.get("BOT_TOKEN", "")
CHAT_ID        = os.environ.get("CHAT_ID", "")
FINNHUB_TOKEN  = os.environ.get("FINNHUB_TOKEN", "")   # бесплатно: finnhub.io
POLL_INTERVAL  = 5

# Позиции и кэш можно переопределить через /pos и /cash,
# при рестарте подгружаются из ENV-переменной POSITIONS_JSON
DEFAULT_CASH = 100_000.0
DEFAULT_POSITIONS = {
    "VWCE": 4.0,   "SXR8": 1.0,   "SXRV": 0.2,
    "IGLD": 3.0,   "JGPI": 1000.0,"QDVB": 70.0,
    "EIMI": 5.0,   "BRNT": 20.0,  "BTIC": 8.0,
    "XEON": 70.0,  "XDEW": 1.0,
}

TICKERS = {
    "VWCE": "XETR:VWCE",
    "SXR8": "XETR:SXR8",
    "SXRV": "XETR:SXRV",
    "IGLD": "XETR:IGLD",
    "JGPI": "XETR:JGPI",
    "QDVB": "XETR:QDVB",
    "EIMI": "LSE:EIMI",
    "BRNT": "BVME:BRNT",          # ← исправлено (ETF, не фьючерс)
    "BTIC": "XETR:BTIC",
    "XEON": "XETR:XEON",
    "XDEW": "XETR:XDEW",
}
REV_TICKERS = {v: k for k, v in TICKERS.items()}
VIX_TICKER  = "TVC:VIX"

TARGET_WEIGHTS = {
    "VWCE": 30.0, "SXR8": 10.0, "SXRV": 10.0,
    "IGLD": 10.0, "JGPI": 10.0, "EIMI":  7.0,
    "QDVB":  5.0, "BRNT":  5.0, "BTIC":  3.0,
    "XDEW": 10.0,
}

# ─────────────────────────────────────────
#  STATE  (переживает рестарт через JSON)
# ─────────────────────────────────────────
def _load_state() -> Tuple[float, Dict[str, float]]:
    raw = os.environ.get("POSITIONS_JSON", "")
    if raw:
        try:
            data = json.loads(raw)
            return float(data.get("cash", DEFAULT_CASH)), data.get("positions", DEFAULT_POSITIONS)
        except Exception:
            pass
    return DEFAULT_CASH, dict(DEFAULT_POSITIONS)

CASH_BALANCE, CURRENT_POSITIONS = _load_state()
last_update_id = -1

# ─────────────────────────────────────────
#  TELEGRAM
# ─────────────────────────────────────────
def send_telegram(text: str) -> None:
    if not BOT_TOKEN or not CHAT_ID:
        print(text)
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": CHAT_ID, "text": text,
                                  "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")

# ─────────────────────────────────────────
#  TRADINGVIEW DATA
# ─────────────────────────────────────────
def get_market_data() -> List[dict]:
    symbols = list(TICKERS.values()) + [VIX_TICKER]
    try:
        r = requests.post(
            "https://scanner.tradingview.com/global/scan",
            json={"symbols": {"tickers": symbols},
                  "columns": ["close", "change", "RSI"]},
            timeout=15
        )
        r.raise_for_status()
        return r.json().get("data", [])
    except Exception as e:
        print(f"TradingView error: {e}")
        return []

def extract_maps(data: List[dict]):
    prices, changes, rsis = {}, {}, {}
    for item in data:
        s = item.get("s")
        d = item.get("d", [])
        if not s or len(d) < 3:
            continue
        prices[s]  = d[0] or 0.0
        changes[s] = d[1] or 0.0
        rsis[s]    = d[2]
    return prices, changes, rsis

# ─────────────────────────────────────────
#  FINNHUB NEWS
# ─────────────────────────────────────────
def get_market_news() -> List[str]:
    """Возвращает топ-5 финансовых заголовков дня."""
    if not FINNHUB_TOKEN:
        return []
    try:
        r = requests.get(
            "https://finnhub.io/api/v1/news",
            params={"category": "general", "token": FINNHUB_TOKEN},
            timeout=10
        )
        r.raise_for_status()
        items = r.json()[:5]
        return [f"• {item['headline']}" for item in items if "headline" in item]
    except Exception as e:
        print(f"Finnhub error: {e}")
        return []

# ─────────────────────────────────────────
#  SMART DAILY CONCLUSION
# ─────────────────────────────────────────
def generate_conclusion(prices, changes, rsis, vix_val: float, news: List[str]) -> str:
    """Генерирует умный вывод дня на основе данных + новостей."""
    signals = []

    # VIX анализ
    if vix_val > 25:
        signals.append("🚨 Рынок в панике (VIX>25) — держать кэш")
    elif vix_val > 18:
        signals.append("⚠️ Умеренная тревога на рынке (VIX>18)")
    else:
        signals.append("✅ Рынок спокоен (VIX<18)")

    # Перегретые позиции
    hot = [REV_TICKERS.get(t, t) for t, r in rsis.items()
           if r and r > 70 and t != VIX_TICKER]
    if hot:
        signals.append(f"🔴 Перегреты (RSI>70): {', '.join(hot)} — не докупать")

    # Перепроданные позиции
    cold = [REV_TICKERS.get(t, t) for t, r in rsis.items()
            if r and r < 30 and t != VIX_TICKER]
    if cold:
        signals.append(f"🟢 Перепроданы (RSI<30): {', '.join(cold)} — возможна покупка")

    # Резкие движения
    movers = [(REV_TICKERS.get(t, t), c) for t, c in changes.items()
              if abs(c) > 3 and t != VIX_TICKER]
    for name, chg in sorted(movers, key=lambda x: abs(x[1]), reverse=True)[:3]:
        arrow = "📈" if chg > 0 else "📉"
        signals.append(f"{arrow} {name} резко {'вырос' if chg > 0 else 'упал'}: {chg:+.1f}%")

    conclusion = "\n".join(signals)

    # Добавляем топ-новость если есть
    if news:
        conclusion += f"\n\n📰 Главное в новостях:\n{news[0]}"

    return conclusion

# ─────────────────────────────────────────
#  ВЕЧЕРНЯЯ СВОДКА (21:00 МСК)
# ─────────────────────────────────────────
def generate_evening_report() -> str:
    data = get_market_data()
    if not data:
        return "❌ Ошибка получения данных."

    prices, changes, rsis = extract_maps(data)
    news = get_market_news()

    vix_val = prices.get(VIX_TICKER, 0.0)
    vix_icon = "🟢" if vix_val < 15 else "🟡" if vix_val < 25 else "🔴"

    # Капитал
    total_assets = sum(
        prices.get(TICKERS[n], 0.0) * q
        for n, q in CURRENT_POSITIONS.items() if TICKERS.get(n) in prices
    )
    total = total_assets + CASH_BALANCE
    cash_pct = (CASH_BALANCE / total * 100) if total > 0 else 0

    # Лидеры и аутсайдеры
    day_changes = [
        (REV_TICKERS.get(t, t), c)
        for t, c in changes.items() if t != VIX_TICKER and t in REV_TICKERS
    ]
    winners = sorted([x for x in day_changes if x[1] > 0], key=lambda x: x[1], reverse=True)[:3]
    losers  = sorted([x for x in day_changes if x[1] < 0], key=lambda x: x[1])[:3]

    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))

    lines = []
    lines.append(f"╔══════════════════════════════╗")
    lines.append(f"   🌙 ВЕЧЕРНЯЯ СВОДКА ПОРТФЕЛЯ")
    lines.append(f"   {now.strftime('%d.%m.%Y')} • {now.strftime('%H:%M')} МСК")
    lines.append(f"╚══════════════════════════════╝")
    lines.append("")
    lines.append(f"💼 Капитал:  `{total:,.0f} €`")
    lines.append(f"💵 Кэш:      `{CASH_BALANCE:,.0f} €` ({cash_pct:.0f}%)")
    lines.append(f"📊 VIX:      `{vix_val:.2f}` {vix_icon}")
    lines.append("")

    # Лидеры
    if winners:
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("🏆 ЛИДЕРЫ ДНЯ")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        for name, chg in winners:
            tv = TICKERS.get(name)
            p  = prices.get(tv, 0)
            r  = rsis.get(tv)
            rsi_str = f"RSI {r:.0f}" if r else "RSI n/a"
            lines.append(f"🟢 {name:<6} {p:>8.2f}  {chg:+.2f}%  {rsi_str}")
        lines.append("")

    # Аутсайдеры
    if losers:
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("🔻 АУТСАЙДЕРЫ ДНЯ")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        for name, chg in losers:
            tv = TICKERS.get(name)
            p  = prices.get(tv, 0)
            r  = rsis.get(tv)
            rsi_str = f"RSI {r:.0f}" if r else "RSI n/a"
            lines.append(f"🔴 {name:<6} {p:>8.2f}  {chg:+.2f}%  {rsi_str}")
        lines.append("")

    # Все позиции
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("📋 ВСЕ ПОЗИЦИИ")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    for name, tv in TICKERS.items():
        if tv not in prices:
            lines.append(f"⚪ {name:<6}  н/д")
            continue
        p   = prices[tv]
        chg = changes.get(tv, 0.0)
        rsi = rsis.get(tv)
        safe_rsi = rsi or 50.0
        sig = "🔴" if safe_rsi > 70 else "🟢" if safe_rsi < 30 else "⚪️"
        rsi_warn = "❗" if safe_rsi > 75 or safe_rsi < 25 else ""
        lines.append(f"{sig} {name:<6} {p:>8.2f}  {chg:>+6.2f}%  RSI {safe_rsi:.0f}{rsi_warn}")
    lines.append("")

    # Сигналы ребалансировки
    alerts = []
    for name, tv in TICKERS.items():
        if tv not in prices:
            continue
        p          = prices[tv]
        rsi        = rsis.get(tv) or 50.0
        target_pct = TARGET_WEIGHTS.get(name, 0.0)
        cur_val    = p * CURRENT_POSITIONS.get(name, 0.0)
        cur_pct    = (cur_val / total * 100) if total > 0 else 0
        diff       = (total * target_pct / 100) - cur_val

        if rsi > 75:
            alerts.append(f"🚨 {name} — RSI {rsi:.0f}, перегрет!")
        elif rsi < 25:
            alerts.append(f"🔥 {name} — RSI {rsi:.0f}, перепродан!")

        if abs(cur_pct - target_pct) > 5 and target_pct > 0:
            if diff < -p:
                qty = abs(diff) / p
                alerts.append(f"⚖️ {name} — перевес {cur_pct:.1f}% (цель {target_pct:.0f}%), продать ~{qty:.0f} шт.")
            elif diff > p:
                qty = diff / p
                alerts.append(f"🛒 {name} — недовес {cur_pct:.1f}% (цель {target_pct:.0f}%), докупить ~{qty:.0f} шт.")

    if alerts:
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("⚠️ СИГНАЛЫ")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        for a in alerts:
            lines.append(a)
        lines.append("")

    # Новости
    if news:
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("📰 НОВОСТИ ДНЯ")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        for n in news[:3]:
            lines.append(n)
        lines.append("")

    # Вывод дня
    conclusion = generate_conclusion(prices, changes, rsis, vix_val, news)
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 ВЫВОД ДНЯ")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(conclusion)
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    return "\n".join(lines)

# ─────────────────────────────────────────
#  ЧАСОВЫЕ АЛЕРТЫ
# ─────────────────────────────────────────
def check_alerts() -> None:
    data = get_market_data()
    if not data:
        return
    prices, changes, rsis = extract_maps(data)
    vix_val = prices.get(VIX_TICKER, 0.0)
    vix_s = "🟢" if vix_val < 15 else "🟡" if vix_val < 25 else "🔴"

    alerts = []
    for symbol, price in prices.items():
        if symbol == VIX_TICKER:
            continue
        name = REV_TICKERS.get(symbol, symbol)
        chg  = changes.get(symbol, 0.0)
        rsi  = rsis.get(symbol)
        if rsi and rsi > 75:
            alerts.append(f"⚠️ {name} перегрет (RSI: {rsi:.0f})")
        elif rsi and rsi < 25:
            alerts.append(f"🔥 {name} перепродан (RSI: {rsi:.0f})")
        if abs(chg) > 4.0:
            alerts.append(f"📊 Резкое движение {name}: {chg:+.2f}%")

    if vix_val > 25:
        alerts.insert(0, f"🚨 VIX {vix_val:.1f} — ПАНИКА на рынке!")

    if not alerts:
        return  # тихий час — не спамим

    msg  = f"🔔 *ЧАСОВОЙ МОНИТОРИНГ*\n"
    msg += f"📊 VIX: `{vix_val:.2f}` {vix_s}\n\n"
    msg += "\n".join(alerts)
    send_telegram(msg)

# ─────────────────────────────────────────
#  КОМАНДЫ TELEGRAM
# ─────────────────────────────────────────
def handle_commands() -> None:
    global last_update_id, CASH_BALANCE

    if not BOT_TOKEN:
        return
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates",
            params={"offset": last_update_id + 1, "timeout": 1},
            timeout=5
        )
        resp.raise_for_status()
    except Exception as e:
        print(f"getUpdates error: {e}")
        return

    for update in resp.json().get("result", []):
        last_update_id = update.get("update_id", last_update_id)
        msg  = update.get("message", {})

        # Защита: игнорируем чужие чаты
        if str(msg.get("chat", {}).get("id", "")) != str(CHAT_ID):
            continue

        text = (msg.get("text") or "").strip()

        if text == "/help":
            send_telegram(
                "📖 *Доступные команды:*\n\n"
                "/report — полная вечерняя сводка\n"
                "/alerts — только сигналы тревоги\n"
                "/pos TICKER N — обновить позицию\n"
                "  _пример: /pos VWCE 10_\n"
                "/cash СУММА — обновить кэш\n"
                "  _пример: /cash 50000_\n"
                "/debug TICKER — детали по тикеру\n"
                "/help — эта справка"
            )

        elif text == "/report":
            send_telegram("⏳ Собираю данные...")
            send_telegram(generate_evening_report())

        elif text == "/alerts":
            check_alerts()

        elif text.startswith("/cash"):
            parts = text.split()
            if len(parts) != 2:
                send_telegram("⚠️ Формат: /cash 50000")
                continue
            try:
                CASH_BALANCE = float(parts[1])
                send_telegram(f"✅ Кэш обновлён: `{CASH_BALANCE:,.0f} €`")
            except ValueError:
                send_telegram("⚠️ Сумма должна быть числом.")

        elif text.startswith("/pos"):
            parts = text.split()
            if len(parts) != 3:
                send_telegram("⚠️ Формат: /pos VWCE 10")
                continue
            symbol = parts[1].upper()
            try:
                qty = float(parts[2])
                CURRENT_POSITIONS[symbol] = qty
                send_telegram(f"✅ {symbol}: `{qty}` шт.")
            except ValueError:
                send_telegram("⚠️ Количество должно быть числом.")

        elif text.startswith("/debug"):
            parts = text.split()
            if len(parts) != 2:
                send_telegram("⚠️ Формат: /debug VWCE")
                continue
            send_telegram(_debug(parts[1]))

        else:
            if text.startswith("/"):
                send_telegram("❓ Неизвестная команда. Напиши /help")

def _debug(symbol: str) -> str:
    data = get_market_data()
    if not data:
        return "❌ Нет данных."
    prices, changes, rsis = extract_maps(data)
    sym = symbol.upper()
    tv  = VIX_TICKER if sym == "VIX" else TICKERS.get(sym)
    if not tv:
        return f"⚠️ Неизвестный тикер `{sym}`. Доступно: {', '.join(TICKERS)}, VIX"
    if tv not in prices:
        return f"⚠️ Нет рыночных данных для `{sym}`."
    p   = prices[tv]
    chg = changes.get(tv, 0.0)
    rsi = rsis.get(tv)
    lines = [
        f"🐞 *DEBUG {sym}*",
        f"Символ TV: `{tv}`",
        f"Цена:      `{p:.4f}`",
        f"Изм/день:  `{chg:+.2f}%`",
        f"RSI:       `{rsi:.2f}`" if rsi else "RSI: n/a",
    ]
    if sym != "VIX":
        qty = CURRENT_POSITIONS.get(sym, 0.0)
        lines.append(f"Позиция:   `{qty}` шт. (~`{qty*p:,.2f} €`)")
    return "\n".join(lines)

# ─────────────────────────────────────────
#  MAIN LOOP
# ─────────────────────────────────────────
if __name__ == "__main__":
    send_telegram(
        "🤖 *Бот запущен*\n"
        "📅 Вечерняя сводка: 21:00 МСК\n"
        "🔔 Часовые алерты: 10:00–21:00 МСК\n"
        "Напиши /help для списка команд."
    )

    last_hour    = -1
    evening_sent = False   # флаг чтобы не слать дважды в 21:00

    while True:
        handle_commands()

        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))
        hour = now.hour

        # Вечерняя сводка в 21:00 МСК
        if hour == 21 and not evening_sent:
            send_telegram("⏳ Готовлю вечернюю сводку...")
            send_telegram(generate_evening_report())
            evening_sent = True
        elif hour != 21:
            evening_sent = False

        # Часовые алерты 10:00–20:59 МСК (только если есть что сообщить)
        if hour != last_hour and 10 <= hour <= 20:
            check_alerts()
            last_hour = hour

        time.sleep(POLL_INTERVAL)

