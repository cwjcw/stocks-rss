# -*- coding: utf-8 -*-
"""
生成每个用户的 RSS：
- 频道含 lastBuildDate / ttl(5)
- 每次生成追加“实时快照”item（guid 含分钟时间戳）
- 条目：价格 + 涨跌幅 + 资金流 + 成交额
- 资金流单位：统一“万元·整数”，正=流入，负=流出
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import List
from datetime import datetime
from zoneinfo import ZoneInfo

import yaml
from feedgen.feed import FeedGenerator

from data_providers import (
    normalize_code,
    get_northbound_overview,
    get_realtime_quotes,
    get_fund_flow_batch,
)

ROOT = Path(__file__).resolve().parents[1]
USERS_DIR = ROOT / "configs" / "users"
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/var/www/stockrss/feeds"))
SITE_LINK = "https://stockrss.cuixiaoyuan.cn"

TOKEN_RE = re.compile(r"^[A-Za-z0-9]{6,32}$")

def load_user_yaml(p: Path) -> dict:
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("YAML 不是字典")
    user_id = str(data.get("user_id", "")).strip()
    token = str(data.get("token", "")).strip()
    title = str(data.get("title", "")).strip() or f"{user_id} 的盯盘"
    stocks = data.get("stocks", [])
    if not user_id or not TOKEN_RE.match(token):
        raise ValueError("user_id/token 不合法（token 需 6–32 位字母或数字）")
    norm_stocks = [normalize_code(s) for s in stocks]
    return {"user_id": user_id, "token": token, "title": title, "stocks": norm_stocks}

def ensure_output_dir():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def to_yi_from_wan(v) -> str:
    """把“万元”格式成“xx.xx 亿 / yyy 万”（用于成交额的友好展示）"""
    if v is None:
        return "—"
    try:
        fv = float(v)
    except Exception:
        return "—"
    yi = fv / 1e4
    return f"{yi:.2f} 亿" if abs(yi) >= 1 else f"{fv:.0f} 万"

def fmt_wan_int(v) -> str:
    """万元整数，保留正负号，带千分位"""
    if v is None:
        return "—"
    try:
        iv = int(v)
    except Exception:
        try:
            iv = int(round(float(v)))
        except Exception:
            return "—"
    return f"{iv:,} 万"

def dir_arrow(v) -> str:
    """方向：↑流入 / ↓流出 / —"""
    if v is None:
        return "—"
    try:
        fv = float(v)
    except Exception:
        return "—"
    return "↑流入" if fv > 0 else ("↓流出" if fv < 0 else "—")

def build_feed_for_user(user: dict) -> Path:
    user_id, token, title, stocks = user["user_id"], user["token"], user["title"], user["stocks"]
    tz = ZoneInfo("Asia/Shanghai")
    now = datetime.now(tz)

    fg = FeedGenerator()
    fg.title(title)
    fg.link(href=SITE_LINK, rel="alternate")
    fg.description("北向资金 / 主力-大中小单净流入 / 实时涨跌 订阅")
    fg.language("zh-cn")
    try:
        fg.lastBuildDate(now)
        fg.ttl(5)
    except Exception:
        pass

    overview = get_northbound_overview()
    quotes = get_realtime_quotes(stocks) if stocks else {}
    flows  = get_fund_flow_batch(stocks) if stocks else {}

    for c in stocks:
        q = quotes.get(c)
        f = flows.get(c)
        name = (q.name if q and q.name else c.upper())

        if q and q.price is not None and q.pct is not None:
            title_item = f"{name} {q.price:.2f}（{q.pct:+.2f}%）"
        elif q and q.price is not None:
            title_item = f"{name} {q.price:.2f}"
        else:
            title_item = f"{name}（行情暂不可用）"

        item = fg.add_entry()
        item.id(f"{user_id}-{c}-{now.strftime('%Y%m%d')}")
        item.title(title_item)
        item.link(href=SITE_LINK)

        if f:
            desc = (
                f"<p>资金流（万元）："
                f"主力 {fmt_wan_int(f.main_wan)}（{dir_arrow(f.main_wan)}） | "
                f"超大单 {fmt_wan_int(f.huge_wan)}（{dir_arrow(f.huge_wan)}） | "
                f"大单 {fmt_wan_int(f.large_wan)}（{dir_arrow(f.large_wan)}） | "
                f"中单 {fmt_wan_int(f.medium_wan)}（{dir_arrow(f.medium_wan)}） | "
                f"小单 {fmt_wan_int(f.small_wan)}（{dir_arrow(f.small_wan)}）"
                f"</p>"
            )
        else:
            desc = "<p>资金流（万元）：暂无数据</p>"

        if q and q.amount_wan is not None:
            desc += f"<p>成交额：{to_yi_from_wan(q.amount_wan)}</p>"

        try:
            item.description(desc)
        except Exception:
            item.content(desc, type="CDATA")

        item.published(now)
        item.updated(now)

    # 快照 item（保证阅读器每次识别有更新）
    snap = fg.add_entry()
    snap.id(f"{user_id}-snapshot-{now.strftime('%Y%m%d%H%M')}")
    snap.title(f"{title} 实时快照 @ {now.strftime('%Y-%m-%d %H:%M')}")
    def nb_text(ov):
        if not ov or ov.get("total") is None:
            return "北向资金：接口暂不可用 / 闭市"
        return f"北向资金（亿元）｜沪股通 {ov['sh']}｜深股通 {ov['sz']}｜合计 {ov['total']}｜时间 {ov['time']}"
    snap_html = f"""
<ul>
  <li>更新时间：{now.strftime('%Y-%m-%d %H:%M:%S')}</li>
  <li>{nb_text(overview)}</li>
  <li>覆盖股票数：{len(stocks)}</li>
</ul>
""".strip()
    try:
        snap.description(snap_html)
    except Exception:
        snap.content(snap_html, type="CDATA")
    snap.published(now)
    snap.updated(now)

    out = OUTPUT_DIR / f"{user_id}-{token}.xml"
    fg.rss_file(out, pretty=True)
    return out

def main():
    ensure_output_dir()
    users = []
    for p in sorted(USERS_DIR.glob("*.yaml")):
        with p.open("rb") as f:
            if f.read(1) == b"<":
                print(f"[SKIP] {p.name} -> 似乎是 HTML，跳过")
                continue
        try:
            users.append(load_user_yaml(p))
        except Exception as e:
            print(f"[SKIP] {p.name} -> {e}")
            continue

    generated: List[str] = []
    for u in users:
        try:
            out = build_feed_for_user(u)
            print(f"[OK] {u['user_id']} → {out}")
            generated.append(out.name)
        except Exception as e:
            print(f"[ERR] {u['user_id']} -> {e}")
    print(f"[DONE] generated feeds: {generated}")

if __name__ == "__main__":
    sys.exit(main())
