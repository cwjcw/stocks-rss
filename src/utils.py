def fmt_yn(v):
    return "—" if v is None else f"{v:,.0f}"

def fmt_pct(v):
    if v is None: return "—"
    sign = "↑" if v >= 0 else "↓"
    return f"{sign}{abs(v):.2f}%"
