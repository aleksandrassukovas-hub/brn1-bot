def format_ticker_details(sym, full_name, p, chg, rsi):
    L = []

    if full_name:
        L.append(f"_{full_name}_")

    L.append(f"Цена: *{p:.4f} €*")
    L.append(f"Изм/день: *{chg:+.2f}%*")
    L.append(f"RSI: *{rsi:.2f}*" if rsi is not None else "RSI: n/a")

    if sym != "VIX":
        qty = CURRENT_POSITIONS.get(sym, 0.0)
        target = TARGET_WEIGHTS.get(sym, 0.0)
        L.append(f"Позиция: *{qty}* шт. (~*{qty * p:,.2f} €*)")
        L.append(f"Цель: *{target:.0f}%*")

    return "\n".join(L)
