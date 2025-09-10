# -*- coding: utf-8 -*-
"""
数据抓取与清洗
- 北向资金概览（容错，单位：亿元）
- A股快照（价格、涨跌幅、成交额〔统一存“万元”〕）
- 个股资金流（主力/超大/大/中/小单净流入：直接用东方财富 push2 接口，统一换算为“万元·整数”）
"""
from __future__ import annotations

import os
import re
import json
from dataclasses import dataclass
from typing import Dict, List, Optional
from datetime import datetime, timezone, timedelta

import requests
import pandas as pd
import akshare as ak  # 保留：用于北向/行情

TZ_SH = timezone(timedelta(hours=8))

# --------------------------- 工具 ---------------------------

def normalize_code(code: str) -> str:
    """统一股票代码为带交易所前缀（sh/sz）。"""
    code = str(code).strip().lower()
    if re.match(r'^(sh|sz)\d{6}$', code):
        return code
    m = re.match(r'^\d{6}$', code)
    if not m:
        raise ValueError(f"非法股票代码：{code}")
    # 6/9/5 => 上交所；0/1/2/3 => 深交所（覆盖 000/001/002/300/301 等）
    return ('sh' if code[0] in '695' else 'sz') + code

def now_str() -> str:
    return datetime.now(TZ_SH).strftime("%Y-%m-%d %H:%M:%S")

def _to_float_maybe(val) -> Optional[float]:
    if val is None:
        return None
    try:
        x = str(val).replace('亿元', '').replace('万', '').replace(',', '').replace('%', '').strip()
        if x == '' or x == '—' or x.lower() == 'nan':
            return None
        return float(x)
    except Exception:
        return None

# --------------------------- 北向资金 ---------------------------

def get_northbound_overview() -> Dict[str, Optional[float]]:
    """
    {"sh": 12.34, "sz": -5.67, "total": 6.67, "time": "..."}，单位：亿元
    """
    ts = now_str()
    sh = sz = total = None
    try:
        df = ak.stock_hsgt_fund_flow_summary_em()
        row = df.tail(1).squeeze()
        sh_cols = ["沪股通-净流入", "沪股通净流入", "沪股通"]
        sz_cols = ["深股通-净流入", "深股通净流入", "深股通"]
        tt_cols = ["北向资金-净流入", "北向资金净流入", "北向资金"]
        for c in sh_cols:
            if c in df.columns: sh = _to_float_maybe(row[c]); break
        for c in sz_cols:
            if c in df.columns: sz = _to_float_maybe(row[c]); break
        for c in tt_cols:
            if c in df.columns: total = _to_float_maybe(row[c]); break
        if total is None and (sh is not None and sz is not None):
            total = round(sh + sz, 2)
    except Exception:
        pass
    return {
        "sh": None if sh is None else round(sh, 2),
        "sz": None if sz is None else round(sz, 2),
        "total": None if total is None else round(total, 2),
        "time": ts,
    }

# --------------------------- A股快照（统一成交额为“万元”） ---------------------------

@dataclass
class Quote:
    code: str
    name: str
    price: Optional[float]
    pct: Optional[float]          # 涨跌幅 %
    amount_wan: Optional[float]   # 成交额（统一存为“万元”）
    time: str

def _normalize_amount_to_wan(raw_val: Optional[float]) -> Optional[float]:
    if raw_val is None:
        return None
    try:
        v = float(raw_val)
    except Exception:
        return None
    # >=1e8 视为“元”，/1e4 -> 万元；否则按“万元”
    return v/1e4 if v >= 1e8 else v

def get_realtime_quotes(codes: List[str]) -> Dict[str, Quote]:
    norm_codes = [normalize_code(c) for c in codes]
    wants = set([c[-6:] for c in norm_codes])
    res: Dict[str, Quote] = {}
    ts = now_str()
    try:
        spot = ak.stock_zh_a_spot_em()
        spot = spot[spot['代码'].astype(str).isin(wants)]
        for _, r in spot.iterrows():
            num = str(r['代码']).zfill(6)
            full = normalize_code(num)
            amt_wan = _normalize_amount_to_wan(_to_float_maybe(r.get('成交额')))
            res[full] = Quote(
                code=full,
                name=str(r.get('名称', '')),
                price=_to_float_maybe(r.get('最新价')),
                pct=_to_float_maybe(r.get('涨跌幅')),
                amount_wan=amt_wan,
                time=ts
            )
    except Exception:
        pass
    for c in norm_codes:
        if c not in res:
            res[c] = Quote(code=c, name="", price=None, pct=None, amount_wan=None, time=ts)
    return res

# --------------------------- 个股资金流（东方财富 push2，统一为“万元·整数”） ---------------------------

@dataclass
class FundFlow:
    code: str
    main_wan: Optional[int]     # 主力净额（万元·整数，正=流入，负=流出）
    huge_wan: Optional[int]     # 超大单（万元·整数）
    large_wan: Optional[int]    # 大单（万元·整数）
    medium_wan: Optional[int]   # 中单（万元·整数）
    small_wan: Optional[int]    # 小单（万元·整数）
    main_pct: Optional[float]   # 主力净占比（%）
    time: str

def _code_to_secid(code: str) -> str:
    c = normalize_code(code)
    mkt = '1' if c.startswith('sh') else '0'  # 1=上交所, 0=深交所
    return f"{mkt}.{c[-6:]}"

def _yuan_to_wan_int(v: Optional[float]) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(round(float(v) / 1e4))
    except Exception:
        return None

def get_fund_flow_batch(codes: List[str]) -> Dict[str, FundFlow]:
    """
    直接用东方财富 push2 聚合接口，一次查多只，字段单位=元；这里统一转为“万元·整数”。
    """
    res: Dict[str, FundFlow] = {}
    if not codes:
        return res

    # 组装 secids
    norm = [normalize_code(c) for c in codes]
    code_map = {normalize_code(c)[-6:]: normalize_code(c) for c in codes}  # '600519' -> 'sh600519'
    secids = ','.join([_code_to_secid(c) for c in norm])

    url = "https://push2.eastmoney.com/api/qt/ulist.np/get"
    params = {
        "fltt": "2", "invt": "2",
        "secids": secids,
        "fields": "f12,f14,f62,f184,f66,f69,f72,f75"
    }
    headers = {
        "Referer": "https://quote.eastmoney.com/",
        "User-Agent": "Mozilla/5.0"
    }

    ts = now_str()
    try:
        r = requests.get(url, params=params, headers=headers, timeout=8)
        r.raise_for_status()
        j = r.json()
        diff = (j.get("data") or {}).get("diff") or []
        for item in diff:
            code_num = str(item.get("f12") or "").zfill(6)
            code_full = code_map.get(code_num)  # 'sh600519' / 'sz000981'
            if not code_full:
                continue
            main_yuan  = _to_float_maybe(item.get("f62"))
            huge_yuan  = _to_float_maybe(item.get("f66"))
            large_yuan = _to_float_maybe(item.get("f69"))
            medium_yuan= _to_float_maybe(item.get("f72"))
            small_yuan = _to_float_maybe(item.get("f75"))
            main_pct   = _to_float_maybe(item.get("f184"))

            res[code_full] = FundFlow(
                code=code_full,
                main_wan=_yuan_to_wan_int(main_yuan),
                huge_wan=_yuan_to_wan_int(huge_yuan),
                large_wan=_yuan_to_wan_int(large_yuan),
                medium_wan=_yuan_to_wan_int(medium_yuan),
                small_wan=_yuan_to_wan_int(small_yuan),
                main_pct=main_pct,
                time=ts
            )
    except Exception as e:
        # 失败则全部置空（不影响行情/北向）
        if os.environ.get("SRSS_DEBUG") == "1":
            print("[DEBUG] em fundflow error:", repr(e))

    # 补齐没返回的股票
    for c in norm:
        if c not in res:
            res[c] = FundFlow(code=c, main_wan=None, huge_wan=None, large_wan=None,
                              medium_wan=None, small_wan=None, main_pct=None, time=ts)
    return res
