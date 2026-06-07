import os
import time
import json
import datetime
import requests
from typing import Dict, List, Tuple

# ─────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────
BOT_TOKEN     = os.environ.get("BOT_TOKEN", "")
CHAT_ID       = os.environ.get("CHAT_ID", "")
FINNHUB_TOKEN = os.environ.get("FINNHUB_TOKEN", "")
POLL_INTERVAL = 5

# ─── РАСПИСАНИЕ (время МСК, UTC+3) ───
WORK_DAYS       = {0, 1, 2, 3, 4}   # Пн–Пт (0 = понедельник, 6 = воскресенье)
WORK_START_HOUR = 9                 # начало рабочего дня
WORK_END_HOUR   = 18                # конец рабочего дня
MORNING_HOUR    = 9                 # час утренней сводки
EVENING_HOUR    = 18                # час вечерней сводки

DEFAULT_CASH = 100_000.0
DEFAULT_POSITIONS = {
    "VWCE": 4.0,    "SXR8": 1.0,   "SXRV": 0.2,
    "IGLD": 3.0,    "JGPI": 1000.0,"QDVB": 70.0,
    "EIMI": 5.0,    "BRNT": 20.0,  "BTIC": 8.0,
    "XEON": 70.0,   "XDEW": 1.0,
}

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

TICKER_NAMES = {
    "VWCE": "Vanguard All-World",
    "SXR8": "iShares S&P 500",
    "SXRV": "iShares NASDAQ 100",
    "IGLD": "iShares Physical Gold",
    "JGPI": "JPM Global Equity Premium",
    "QDVB": "iShares MSCI USA Quality",
    "EIMI": "iShares MSCI Emerging Markets",
    "BRNT": "WisdomTree Brent Crude",
    "BTIC": "Invesco Physical Bitcoin",
    "XEON": "Xtrackers EUR Overnight",
    "XDEW": "Xtrackers MSCI World ESG",
}

# ─────────────────────────────────────────
#  ВРЕМЯ И РАСПИСАНИЕ
# ─────────────────────────────────────────
def now_msk() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3)))

def is_working_day(now: datetime.datetime) -> bool:
    return now.weekday() in WORK_DAYS

# ─────────────────────────────────────────
#  STATE
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
        requests.post(
            url,
            data={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"},
            timeout=10
        )
    except Exception as e:
        print(f"Telegram error: {e}")

# ─────────────────────────────────────────
#  TRADINGVIEW
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
#  FINNHUB NEWS + ПЕРЕВОД
# ─────────────────────────────────────────
def get_market_news(limit: int = 5) -> List[dict]:
    if not FINNHUB_TOKEN:
        return []
    try:
        r = requests.get(
            "https://finnhub.io/api/v1/news",
            params={"category": "general", "token": FINNHUB_TOKEN},
            timeout=10
        )
        r.raise_for_status()
        return r.json()[:limit]
    except Exception as e:
        print(f"Finnhub error: {e}")
        return []

def translate_headline(text: str) -> str:
    try:
        r = requests.get(
            "https://api.mymemory.translated.net/get",
            params={"q": text, "langpair": "en|ru"},
            timeout=8
        )
        result = r.json().get("responseData", {}).get("translatedText", "")
        return result if result else text
    except Exception:
        return text

def get_news_lines(limit: int = 3) -> List[str]:
    items = get_market_news(limit)
    lines = []
    for item in items:
        headline = item.get("headline", "")
        if headline:
            lines.append(f"• {translate_headline(headline)}")
    return lines

# ─────────────────────────────────────────
#  ВЫВОД ДНЯ
# ─────────────────────────────────────────
def generate_conclusion(prices, changes, rsis, vix_val: float, news_lines: List[str]) -> str:
    signals = []

    if vix_val > 25:
        signals.append("🚨 Рынок в панике — держать кэш")
    elif vix_val > 18:
        signals.append("⚠️ Умеренная тревога — осторожность")
    else:
        signals.append("✅ Рынок спокоен — нормальный режим")

    hot = [REV_TICKERS.get(t, t) for t, r in rsis.items()
           if r and r > 70 and t != VIX_TICKER and t in REV_TICKERS]
    if hot:
        signals.append(f"🔴 Перегреты: {', '.join(hot)} — не докупать")

    cold = [REV_TICKERS.get(t, t) for t, r in rsis.items()
            if r and r < 30 and t != VIX_TICKER and t in REV_TICKERS]
    if cold:
        signals.append(f"🟢 Перепроданы: {', '.join(cold)} — возможна покупка")

    movers = [
        (REV_TICKERS.get(t, t), c)
        for t, c in changes.items()
        if abs(c) > 3 and t != VIX_TICKER and t in REV_TICKERS
    ]
    for name, chg in sorted(movers, key=lambda x: abs(x[1]), reverse=True)[:3]:
        arrow = "📈" if chg > 0 else "📉"
        direction = "вырос" if chg > 0 else "упал"
        signals.append(f"{arrow} {name} резко {direction}: {chg:+.1f}%")

    result = "\n".join(signals)
    if news_lines:
        result += f"\n\n📰 Главное:\n{news_lines[0]}"
    return result

# ─────────────────────────────────────────
#  УТРЕННЯЯ СВОДКА
# ─────────────────────────────────────────
def generate_morning_report() -> str:
    data = get_market_data()
    if not data:
        return "❌ Ошибка получения данных."

    prices, changes, rsis = extract_maps(data)
    news_lines = get_news_lines(3)
    vix_val  = prices.get(VIX_TICKER, 0.0)
    vix_icon = "🟢" if vix_val < 15 else "🟡" if vix_val < 25 else "🔴"
    now = now_msk()

    L = []
    L.append(f"*🌅 УТРЕННЯЯ СВОДКА*")
    L.append(f"_{now.strftime('%d.%m.%Y')} · {now.strftime('%H:%M')} МСК_")
    L.append("")
    L.append(f"📊 VIX: *{vix_val:.2f}* {vix_icon}")
    L.append("")

    L.append("*📋 Позиции на открытии*")
    for name, tv in TICKERS.items():
        if tv not in prices:
            continue
        p   = prices[tv]
        rsi = rsis.get(tv) or 50.0
        sig = "🔴" if rsi > 70 else "🟢" if rsi < 30 else "⚪️"
        L.append(f"{sig} *{name}*  {p:.2f}   RSI {rsi:.0f}")

    watch = []
    for name, tv in TICKERS.items():
        if tv not in prices:
            continue
        rsi = rsis.get(tv) or 50.0
        if rsi > 72:
            watch.append(f"⚠️ {name} — RSI {rsi:.0f}, возможна коррекция")
        elif rsi < 28:
            watch.append(f"👀 {name} — RSI {rsi:.0f}, следи за отскоком")

    if watch:
        L.append("")
        L.append("*🎯 Следи сегодня*")
        for w in watch:
            L.append(w)

    if news_lines:
        L.append("")
        L.append("*📰 Новости утра*")
        for n in news_lines:
            L.append(n)

    L.append("")
    L.append("_Удачного торгового дня! 💼_")
    return "\n".join(L)

# ─────────────────────────────────────────
#  ВЕЧЕРНЯЯ СВОДКА
# ─────────────────────────────────────────
def generate_evening_report() -> str:
    data = get_market_data()
    if not data:
        return "❌ Ошибка получения данных."

    prices, changes, rsis = extract_maps(data)
    news_lines = get_news_lines(3)
    vix_val  = prices.get(VIX_TICKER, 0.0)
    vix_icon = "🟢" if vix_val < 15 else "🟡" if vix_val < 25 else "🔴"

    total_assets = sum(
        prices.get(TICKERS[n], 0.0) * q
        for n, q in CURRENT_POSITIONS.items() if TICKERS.get(n) in prices
    )
    total    = total_assets + CASH_BALANCE
    cash_pct = (CASH_BALANCE / total * 100) if total > 0 else 0

    day_changes = [
        (REV_TICKERS.get(t, t), c)
        for t, c in changes.items() if t != VIX_TICKER and t in REV_TICKERS
    ]
    winners = sorted([x for x in day_changes if x[1] > 0], key=lambda x: x[1], reverse=True)[:3]
    losers  = sorted([x for x in day_changes if x[1] < 0], key=lambda x: x[1])[:3]
    now = now_msk()

    L = []
    L.append(f"*🌙 ВЕЧЕРНЯЯ СВОДКА*")
    L.append(f"_{now.strftime('%d.%m.%Y')} · {now.strftime('%H:%M')} МСК_")
    L.append("")
    L.append(f"💼 Капитал: *{total:,.0f} €*")
    L.append(f"💵 Кэш: *{CASH_BALANCE:,.0f} €* ({cash_pct:.0f}%)")
    L.append(f"📊 VIX: *{vix_val:.2f}* {vix_icon}")

    if winners:
        L.append("")
        L.append("*🏆 Лидеры дня*")
        for name, chg in winners:
            tv = TICKERS.get(name)
            p  = prices.get(tv, 0)
            r  = rsis.get(tv)
            rsi_str = f"RSI {r:.0f}" if r else ""
            L.append(f"🟢 *{name}*  {p:.2f}  {chg:+.2f}%  {rsi_str}")

    if losers:
        L.append("")
        L.append("*🔻 Аутсайдеры дня*")
        for name, chg in losers:
            tv = TICKERS.get(name)
            p  = prices.get(tv, 0)
            r  = rsis.get(tv)
            rsi_str = f"RSI {r:.0f}" if r else ""
            L.append(f"🔴 *{name}*  {p:.2f}  {chg:+.2f}%  {rsi_str}")

    L.append("")
    L.append("*📋 Все позиции*")
    for name, tv in TICKERS.items():
        if tv not in prices:
            L.append(f"⚪️ *{name}*  н/д")
            continue
        p        = prices[tv]
        chg      = changes.get(tv, 0.0)
        rsi      = rsis.get(tv)
        safe_rsi = rsi or 50.0
        sig      = "🔴" if safe_rsi > 70 else "🟢" if safe_rsi < 30 else "⚪️"
        warn     = "❗" if safe_rsi > 75 or safe_rsi < 25 else ""
        L.append(f"{sig} *{name}*  {p:.2f}  {chg:+.2f}%  RSI {safe_rsi:.0f}{warn}")

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
                alerts.append(f"⚖️ {name} — перевес {cur_pct:.1f}% → цель {target_pct:.0f}%, продать ~{qty:.0f} шт.")
            elif diff > p:
                qty = diff / p
                alerts.append(f"🛒 {name} — недовес {cur_pct:.1f}% → цель {target_pct:.0f}%, докупить ~{qty:.0f} шт.")

    if alerts:
        L.append("")
        L.append("*⚠️ Сигналы*")
        for a in alerts:
            L.append(a)

    if news_lines:
        L.append("")
        L.append("*📰 Новости дня*")
        for n in news_lines:
            L.append(n)

    conclusion = generate_conclusion(prices, changes, rsis, vix_val, news_lines)
    L.append("")
    L.append("*💡 Вывод дня*")
    L.append(conclusion)

    return "\n".join(L)

# ─────────────────────────────────────────
#  РЕБАЛАНСИРОВКА
# ─────────────────────────────────────────
def generate_rebalance_report() -> str:
    data = get_market_data()
    if not data:
        return "❌ Ошибка получения данных."

    prices, _, _ = extract_maps(data)
    total_assets = sum(
        prices.get(TICKERS[n], 0.0) * q
        for n, q in CURRENT_POSITIONS.items() if TICKERS.get(n) in prices
    )
    total = total_assets + CASH_BALANCE
    now = now_msk()

    L = []
    L.append("*⚖️ ПЛАН РЕБАЛАНСИРОВКИ*")
    L.append(f"_{now.strftime('%d.%m.%Y')} · {now.strftime('%H:%M')} МСК_")
    L.append("")
    L.append(f"💼 Капитал: *{total:,.0f} €*")
    L.append(f"💵 Кэш: *{CASH_BALANCE:,.0f} €*")

    buy_list, sell_list = [], []
    for name, target_pct in TARGET_WEIGHTS.items():
        tv = TICKERS.get(name)
        if not tv or tv not in prices:
            continue
        p        = prices[tv]
        qty      = CURRENT_POSITIONS.get(name, 0.0)
        cur_val  = p * qty
        cur_pct  = (cur_val / total * 100) if total > 0 else 0
        diff     = (total * target_pct / 100) - cur_val
        diff_qty = diff / p if p > 0 else 0

        if diff_qty > 0.5:
            buy_list.append(f"🛒 *{name}*  +{diff_qty:.1f} шт.  (+{diff:,.0f} €)  {cur_pct:.1f}%→{target_pct:.0f}%")
        elif diff_qty < -0.5:
            sell_list.append(f"⚖️ *{name}*  -{abs(diff_qty):.1f} шт.  ({diff:,.0f} €)  {cur_pct:.1f}%→{target_pct:.0f}%")

    if sell_list:
        L.append("")
        L.append("*📤 Продать*")
        for s in sell_list:
            L.append(s)

    if buy_list:
        L.append("")
        L.append("*📥 Купить*")
        for b in buy_list:
            L.append(b)

    if not sell_list and not buy_list:
        L.append("")
        L.append("✅ Портфель сбалансирован!")

    L.append("")
    L.append("_⚠️ Расчёт, не финансовый совет._")
    return "\n".join(L)

# ─────────────────────────────────────────
#  ЧАСОВЫЕ АЛЕРТЫ
# ─────────────────────────────────────────
def check_alerts() -> None:
    data = get_market_data()
    if not data:
        return
    prices, changes, rsis = extract_maps(data)
    vix_val = prices.get(VIX_TICKER, 0.0)
    vix_s   = "🟢" if vix_val < 15 else "🟡" if vix_val < 25 else "🔴"

    alerts = []
    if vix_val > 25:
        alerts.append(f"🚨 VIX {vix_val:.1f} — ПАНИКА на рынке!")

    for symbol in prices:
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
            alerts.append(f"📊 {name}: резкое движение {chg:+.2f}%")

    if not alerts:
        return

    L = []
    L.append("*🔔 ЧАСОВОЙ АЛЕРТ*")
    L.append(f"📊 VIX: *{vix_val:.2f}* {vix_s}")
    L.append("")
    L.extend(alerts)
    send_telegram("\n".join(L))

# ─────────────────────────────────────────
#  DEBUG
# ─────────────────────────────────────────
def _debug(symbol: str) -> str:
    data = get_market_data()
    if not data:
        return "❌ Нет данных."
    prices, changes, rsis = extract_maps(data)
    sym = symbol.upper()
    tv  = VIX_TICKER if sym == "VIX" else TICKERS.get(sym)
    if not tv:
        return f"⚠️ Неизвестный тикер `{sym}`.\nДоступно: {', '.join(TICKERS)}, VIX"
    if tv not in prices:
        return f"⚠️ Нет данных для `{sym}`."
    p   = prices[tv]
    chg = changes.get(tv, 0.0)
    rsi = rsis.get(tv)
    full_name = TICKER_NAMES.get(sym, "")
    L = [f"*🐞 DEBUG {sym}*"]
    if full_name:
        L.append(f"_{full_name}_")
    L.append(f"Цена: *{p:.4f} €*")
    L.append(f"Изм/день: *{chg:+.2f}%*")
    L.append(f"RSI: *{rsi:.2f}*" if rsi else "RSI: n/a")
    if sym != "VIX":
        qty    = CURRENT_POSITIONS.get(sym, 0.0)
        target = TARGET_WEIGHTS.get(sym, 0.0)
        L.append(f"Позиция: *{qty}* шт. (~*{qty*p:,.2f} €*)")
        L.append(f"Цель: *{target:.0f}%*")
    return "\n".join(L)

# ─────────────────────────────────────────
#  КОМАНДЫ
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

        if str(msg.get("chat", {}).get("id", "")) != str(CHAT_ID):
            continue

        text = (msg.get("text") or "").strip()

        if text == "/help":
            send_telegram(
                "*📖 Команды бота*\n\n"
                "/report — вечерняя сводка\n"
                "/morning — утренняя сводка\n"
                "/rebalance — план ребалансировки\n"
                "/news — новости рынка\n"
                "/alerts — проверить алерты\n"
                "/snapshot — сохранить позиции\n"
                "/pos TICKER N — обновить позицию\n"
                "/cash СУММА — обновить кэш\n"
                "/debug TICKER — детали по тикеру\n"
                "/help — эта справка"
            )

        elif text == "/report":
            send_telegram("⏳ Собираю данные...")
            send_telegram(generate_evening_report())

        elif text == "/morning":
            send_telegram("⏳ Готовлю утреннюю сводку...")
            send_telegram(generate_morning_report())

        elif text == "/rebalance":
            send_telegram("⏳ Считаю ребалансировку...")
            send_telegram(generate_rebalance_report())

        elif text == "/news":
            send_telegram("⏳ Загружаю новости...")
            lines = get_news_lines(5)
            if lines:
                send_telegram("*📰 Новости рынка*\n\n" + "\n\n".join(lines))
            else:
                send_telegram("⚠️ Новости недоступны. Проверь FINNHUB\\_TOKEN.")

        elif text == "/alerts":
            check_alerts()

        elif text == "/snapshot":
            snapshot = json.dumps({"cash": CASH_BALANCE, "positions": CURRENT_POSITIONS})
            send_telegram(
                "*💾 Сохрани в Railway Variables как POSITIONS\\_JSON:*\n\n"
                f"`{snapshot}`"
            )

        elif text.startswith("/cash"):
            parts = text.split()
            if len(parts) != 2:
                send_telegram("⚠️ Формат: /cash 50000")
                continue
            try:
                CASH_BALANCE = float(parts[1])
                send_telegram(f"✅ Кэш: *{CASH_BALANCE:,.0f} €*\nНапиши /snapshot чтобы сохранить.")
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
                send_telegram(f"✅ {symbol}: *{qty}* шт.\nНапиши /snapshot чтобы сохранить.")
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

# ─────────────────────────────────────────
#  MAIN LOOP
# ─────────────────────────────────────────
if __name__ == "__main__":
    send_telegram(
        "*🤖 Бот запущен*\n\n"
        "🗓 Авто-режим: только по будням (Пн–Пт)\n"
        "🌅 Утренняя сводка: 09:00 МСК\n"
        "🌙 Вечерняя сводка: 18:00 МСК\n"
        "🔔 Алерты: 10:00–17:59 МСК\n\n"
        "Команды (/report, /morning и т.д.) работают всегда.\n"
        "Напиши /help для списка команд."
    )

    last_hour    = -1
    morning_sent = False
    evening_sent = False

    while True:
        # Команды обрабатываются всегда — независимо от дня и часа
        handle_commands()

        now  = now_msk()
        hour = now.hour

        # Автоматические сводки и алерты — только в рабочие дни
        if is_working_day(now):
            if hour == MORNING_HOUR and not morning_sent:
                send_telegram("⏳ Готовлю утреннюю сводку...")
                send_telegram(generate_morning_report())
                morning_sent = True
            elif hour != MORNING_HOUR:
                morning_sent = False

            if hour == EVENING_HOUR and not evening_sent:
                send_telegram("⏳ Готовлю вечернюю сводку...")
                send_telegram(generate_evening_report())
                evening_sent = True
            elif hour != EVENING_HOUR:
                evening_sent = False

            # Часовые алерты строго между сводками: 10:00–17:59 МСК
            if hour != last_hour and WORK_START_HOUR < hour < WORK_END_HOUR:
                check_alerts()
                last_hour = hour
        else:
            # Выходной — сбрасываем флаги, чтобы в понедельник всё сработало штатно
            morning_sent = False
            evening_sent = False

        time.sleep(POLL_INTERVAL)
