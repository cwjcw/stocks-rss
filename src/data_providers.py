# -*- coding: utf-8 -*-
"""
data_providers.py  (TuShare + Eastmoney)
- 北向资金：TuShare pro.moneyflow_hsgt（单位：亿元）
- A股报价/涨跌幅/成交额（万元）：TuShare pro_bar(freq="1min") + daily（补前收）
- 个股资金流：东方财富 push2（单位元 -> 万元·整数；正=流入，负=流出），保留实时性
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd
import requests
import tushare as ts

TS_TOKEN_ENV = "TUSHARE_TOKEN"
_PRO = None  # 全局缓存 TuShare pro()
_NAME_CACHE: Dict[str, str] = {}  # ts_code -> name


# ============== 通用工具 ==============

def _now_cn_str() -> str:
    return pd.Timestamp.now(tz="Asia/Shanghai").strftime("%Y-%m-%d %H:%M:%S")


def _today_ymd() -> str:
    return pd.Timestamp.now(tz="Asia/Shanghai").strftime("%Y%m%d")


def _to_float(x) -> Optional[float]:
    if x is None:
        return None
    try:
        s = str(x).replace(",", "").replace("%", "").strip()
        if s in ("", "—") or s.lower() == "nan":
            return None
        return float(s)
    except Exception:
        return None


def normalize_code(code: str) -> str:
    """
    统一股票代码为带交易所前缀（sh/sz）。
    - 已带前缀：直接返回
    - 纯6位数字：6/9/5 -> 上交所(sh)，0/1/2/3 -> 深交所(sz)
    """
    code = str(code).strip().lower()
    if re.match(r"^(sh|sz)\d{6}$", code):
        return code
    if re.match(r"^\d{6}$", code):
        return ("sh" if code[0] in "695" else "sz") + code
    raise ValueError(f"非法股票代码：{code}")


def _to_ts_code(code_full: str) -> str:
    """sh600519 -> 600519.SH / sz000001 -> 000001.SZ"""
    c = normalize_code(code_full)
    return f"{c[-6:]}.SH" if c.startswith("sh") else f"{c[-6:]}.SZ"


def _get_pro():
    """获取并缓存 TuShare pro()；需要环境变量 TUSHARE_TOKEN。"""
    global _PRO
    if _PRO is not None:
        return _PRO
    token = os.environ.get(TS_TOKEN_ENV, "").strip()
    if not token:
        raise RuntimeError(
            f"未找到环境变量 {TS_TOKEN_ENV}，请先安全配置 TuShare Token（见文末说明）"
        )
    ts.set_token(token)
    _PRO = ts.pro_api()
    return _PRO


def _get_name(ts_code: str) -> str:
    """缓存获取证券简称；失败返回空串，不影响主流程。"""
    if ts_code in _NAME_CACHE:
        return _NAME_CACHE[ts_code]
    try:
        pro = _get_pro()
        df = pro.stock_basic(ts_code=ts_code, fields="ts_code,name")
        if df is not None and not df.empty:
            name = str(df.iloc[0]["name"])
            _NAME_CACHE[ts_code] = name
            return name
    except Exception:
        pass
    return ""


# ============== 北向资金（TuShare 当日/最近一次，亿元） ==============

def get_northbound_overview() -> Dict[str, Optional[float]]:
    """
    使用 TuShare moneyflow_hsgt 获取北向当日（若无则最近一次）净流入（单位：亿元）
    返回: {"sh":float|None, "sz":float|None, "total":float|None, "time": "..."}
    列名兼容：sh_net/hgt（沪股通），sz_net/sgt（深股通），hsgt_net/north_money（北向）
    """
    ts_now = _now_cn_str()
    today = _today_ymd()

    def r2(x):
        return None if x is None else round(float(x), 2)

    sh = sz = total = None
    try:
        pro = _get_pro()
        # 先取今天
        df = pro.moneyflow_hsgt(start_date=today, end_date=today)
        # 今天空则回退近 7 天取最近一条
        if df is None or df.empty:
            df = pro.moneyflow_hsgt(
                start_date=(pd.Timestamp.now(tz="Asia/Shanghai") - pd.Timedelta(days=7)).strftime("%Y%m%d"),
                end_date=today,
            )
        if df is not None and not df.empty:
            df = df.sort_values("trade_date")
            row = df.iloc[-1]

            def pick(row, cols: List[str]):
                for c in cols:
                    if c in row.index:
                        v = _to_float(row[c])
                        if v is not None:
                            return v
                return None

            sh = pick(row, ["sh_net", "hgt", "north_sh", "sh_value"])
            sz = pick(row, ["sz_net", "sgt", "north_sz", "sz_value"])
            total = pick(row, ["hsgt_net", "north_money", "north_net", "north_value"])
            if total is None and (sh is not None and sz is not None):
                total = sh + sz
    except Exception as e:
        if os.environ.get("SRSS_DEBUG") == "1":
            print("[DEBUG] get_northbound_overview tushare error:", repr(e))

    return {"sh": r2(sh), "sz": r2(sz), "total": r2(total), "time": ts_now}


# ============== A股快照（TuShare：价格/涨跌幅/成交额-万元） ==============

@dataclass
class Quote:
    code: str         # 规范化代码，如 sh600519
    name: str
    price: Optional[float]
    pct: Optional[float]          # 涨跌幅 %
    amount_wan: Optional[float]   # 成交额（统一存为“万元”）
    time: str


def _calc_amount_wan_from_minbar(close: Optional[float], vol_hand: Optional[float]) -> Optional[float]:
    """
    用分时 K 的 close 和 vol(手)估算成交额（万元）：
      金额(元) = close * (vol_hand * 100)
      金额(万元) = 上式 / 1e4 = close * vol_hand / 100
    """
    if close is None or vol_hand is None:
        return None
    try:
        return float(close) * float(vol_hand) / 100.0
    except Exception:
        return None


def get_realtime_quotes(codes: List[str]) -> Dict[str, Quote]:
    """
    使用 TuShare pro_bar(freq='1min') 获取最新 1 分钟 close 作为最新价；
    pct 若接口未给，则用 前收/最新价 计算；
    成交额（万元）用公式 close*vol/100（vol 为“手”）。
    """
    res: Dict[str, Quote] = {}
    ts_now = _now_cn_str()
    if not codes:
        return res

    try:
        pro = _get_pro()
    except Exception as e:
        if os.environ.get("SRSS_DEBUG") == "1":
            print("[DEBUG] get_realtime_quotes pro error:", repr(e))
        for c in codes:
            c2 = normalize_code(c)
            res[c2] = Quote(c2, "", None, None, None, ts_now)
        return res

    start_for_min = (pd.Timestamp.now(tz="Asia/Shanghai") - pd.Timedelta(days=3)).strftime("%Y%m%d")

    for code in codes:
        c2 = normalize_code(code)
        ts_code = _to_ts_code(c2)
        price = pct = None
        amt_wan = None
        name = _get_name(ts_code)

        try:
            # 最新 1 分钟（最近3天内，保证有数据）
            dfm = ts.pro_bar(ts_code=ts_code, freq="1min", asset="E", start_date=start_for_min)
            if dfm is not None and not dfm.empty:
                key_time = "trade_time" if "trade_time" in dfm.columns else ("datetime" if "datetime" in dfm.columns else "trade_date")
                dfm = dfm.sort_values(key_time)
                last = dfm.iloc[-1]
                price = _to_float(last.get("close"))
                # 成交额（万）
                amt_wan = _calc_amount_wan_from_minbar(price, _to_float(last.get("vol")))  # vol(手)
                # 优先用接口 pct_chg
                pct = _to_float(last.get("pct_chg"))

            # 计算 pct（若上面没有）
            if pct is None:
                dfd = pro.daily(
                    ts_code=ts_code,
                    start_date=(pd.Timestamp.now(tz="Asia/Shanghai") - pd.Timedelta(days=10)).strftime("%Y%m%d"),
                    end_date=_today_ymd(),
                )
                if dfd is not None and not dfd.empty:
                    dfd = dfd.sort_values("trade_date")
                    prev_close = _to_float(
                        dfd.iloc[-1]["pre_close"] if "pre_close" in dfd.columns
                        else (dfd.iloc[-2]["close"] if len(dfd) >= 2 else None)
                    )
                    if price is not None and prev_close and prev_close != 0:
                        pct = (price / prev_close - 1.0) * 100.0

        except Exception as e:
            if os.environ.get("SRSS_DEBUG") == "1":
                print(f"[DEBUG] quote error {ts_code}:", repr(e))

        res[c2] = Quote(
            code=c2, name=name, price=price, pct=(None if pct is None else round(pct, 2)),
            amount_wan=(None if amt_wan is None else float(f"{amt_wan:.2f}")), time=ts_now
        )

    return res


# ============== 个股资金流（东财 push2，万元·整数，正=流入） ==============

@dataclass
class FundFlow:
    code: str
    main_wan: Optional[int]     # 主力净额（万元·整数；正=流入，负=流出）
    huge_wan: Optional[int]     # 超大单净额
    large_wan: Optional[int]    # 大单净额
    medium_wan: Optional[int]   # 中单净额
    small_wan: Optional[int]    # 小单净额
    time: str


def _secid(code_full: str) -> str:
    """
    东方财富 secid：深 0.XXXXXX，沪 1.XXXXXX
    """
    c = normalize_code(code_full)
    return ("1." if c.startswith("sh") else "0.") + c[-6:]


def _yuan_to_wan_int(v: Optional[float]) -> Optional[int]:
    if v is None:
        return None
    try:
        return int(round(float(v) / 1e4))
    except Exception:
        return None


def get_fund_flow_batch(codes: List[str]) -> Dict[str, FundFlow]:
    """
    东方财富 push2：ulist.np，一次拉多只
      f62 主力净额(元)   f66 超大单(元)   f69 大单(元)   f72 中单(元)   f75 小单(元)
    统一换算为“万元·整数”；正=流入，负=流出（不做符号翻转）
    """
    res: Dict[str, FundFlow] = {}
    if not codes:
        return res

    norm = [normalize_code(c) for c in codes]
    code_map = {c[-6:]: c for c in norm}
    url = "https://push2.eastmoney.com/api/qt/ulist.np/get"
    params = {
        "fltt": "2",
        "invt": "2",
        "secids": ",".join([_secid(c) for c in norm]),
        "fields": "f12,f14,f62,f66,f69,f72,f75",
    }
    headers = {"Referer": "https://quote.eastmoney.com/", "User-Agent": "Mozilla/5.0"}
    ts_now = _now_cn_str()

    try:
        r = requests.get(url, params=params, headers=headers, timeout=8)
        r.raise_for_status()
        j = r.json()
        diff = (j.get("data") or {}).get("diff") or []
        for it in diff:
            num = str(it.get("f12") or "").zfill(6)
            full = code_map.get(num)
            if not full:
                continue
            main  = _yuan_to_wan_int(_to_float(it.get("f62")))
            huge  = _yuan_to_wan_int(_to_float(it.get("f66")))
            large = _yuan_to_wan_int(_to_float(it.get("f69")))
            medium= _yuan_to_wan_int(_to_float(it.get("f72")))
            small = _yuan_to_wan_int(_to_float(it.get("f75")))
            res[full] = FundFlow(
                code=full, main_wan=main, huge_wan=huge, large_wan=large,
                medium_wan=medium, small_wan=small, time=ts_now
            )
    except Exception as e:
        if os.environ.get("SRSS_DEBUG") == "1":
            print("[DEBUG] get_fund_flow_batch error:", repr(e))

    # 补齐没返回的
    for c in norm:
        if c not in res:
            res[c] = FundFlow(
                code=c, main_wan=None, huge_wan=None, large_wan=None,
                medium_wan=None, small_wan=None, time=ts_now
            )
    return res
