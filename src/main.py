import os, time, yaml, re
import pandas as pd
from datetime import datetime, timezone
from data_providers import get_realtime_quotes, get_individual_moneyflow, get_northbound_overview
from rss_builder import build_feed
from utils import fmt_yn, fmt_pct

ROOT = os.path.dirname(os.path.dirname(__file__))

TOKEN_RE = re.compile(r"^[A-Za-z0-9]{6,32}$")
USER_RE  = re.compile(r"^[a-zA-Z0-9_-]{1,32}$")

def compose_items(quotes_df: pd.DataFrame):
    items = []
    north = get_northbound_overview()
    northline = f"北向资金（亿元） | 沪股通 {north['sh']} | 深股通 {north['sz']} | 合计 {north['total']} | 时间 {north['time']}"

    # 如果没有拿到任何个股快照，写一个心跳条目，避免整份 RSS 缺失
    if quotes_df is None or quotes_df.empty:
        items.append({
            "title": f"北向资金心跳 {north.get('total','—')} 亿元",
            "link": "https://stockrss.cuixiaoyuan.cn/",
            "description": f"<p>个股快照暂不可用，稍后自动重试。</p><p>{northline}</p>",
            "guid": f"heartbeat-{int(time.time())}",
            "pubdate": datetime.now(timezone.utc),
        })
        return items

    for _, row in quotes_df.iterrows():
        code = row["code"]
        q_name = row["name"]
        q_price = row["price"]
        q_pct = row["pct_chg"]
        q_amount = row["amount"]
        mf = get_individual_moneyflow(code)
        html = f"""
        <p><b>{q_name}（{code}）</b></p>
        <p>最新价：{q_price}　涨跌幅：{fmt_pct(q_pct)}　成交额：{q_amount} 亿元　时间：{row['time']}</p>
        <p><b>当日净流入（万元）</b><br/>
        主力：{fmt_yn(mf['main'])}　超大单：{fmt_yn(mf['super'])}　大单：{fmt_yn(mf['large'])}　
        中单：{fmt_yn(mf['medium'])}　小单：{fmt_yn(mf['small'])}</p>
        <p>数据时间（资金流）：{mf['ts']}</p>
        <hr/>
        <p>{northline}</p>
        """
        items.append({
            "title": f"{q_name} {fmt_pct(q_pct)} | 最新 {q_price}",
            "link": "https://xueqiu.com/S/" + code.replace("sh","SH").replace("sz","SZ"),
            "description": html,
            "guid": f"{code}-{int(time.time())}",
            "pubdate": datetime.now(timezone.utc),
        })
    return items

def run_for_user(user_cfg: dict, defaults: dict):
    # —— 强制校验 user_id & token ——
    user_id = str(user_cfg.get("user_id","")).strip()
    token   = str(user_cfg.get("token","")).strip()
    if not USER_RE.match(user_id):
        raise ValueError(f"user_id 非法: {user_id}")
    if not TOKEN_RE.match(token):
        raise ValueError(f"{user_id} 缺少合法 token（必须包含 6-32 位字母或数字）")

    stocks = user_cfg["stocks"]
    # 行情抓取失败时，get_realtime_quotes 会返回空表
    quotes = get_realtime_quotes(stocks)

    meta = {
        "title": user_cfg.get("title", defaults["feed"]["title"]),
        "link": defaults["feed"]["link"],
        "description": defaults["feed"]["description"]
    }
    items = compose_items(quotes)
    xml = build_feed(meta, items)

    file_name = f"{user_id}-{token}.xml"
    out_dir = defaults.get("output_dir", os.path.join(ROOT, "public", "feeds"))
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, file_name)
    with open(out, "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"[OK] {user_id} → {out}")
    return file_name
