# -*- coding: utf-8 -*-
"""
data_providers.py
抓取 A 股实时快照、个股资金流、北向资金概览的封装（面向多用户 RSS 生成）。
- 对 AkShare 接口做了重试和兼容处理
- 列名自适配（不同版本 AkShare 字段名可能略有差异）
- 失败时尽量返回空结果而不是抛异常，交给上层兜底

依赖：
    pip install akshare pandas
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional

import pandas as pd
import akshare as ak


# ---------- 小工具 ----------

def _norm_code(code: str) -> str:
    """
    将 6/0 开头代码自动补前缀；已带前缀的保持不变。
    600XXX -> sh600XXX；其他 -> szXXXXXX
    """
    c = code.lower().strip()
    if c.startswith(("sh", "sz")):
        return c
    return ("sh" + c) if c.startswith("6") else ("sz" + c)


def _pick_col(df: pd.DataFrame, candidates: List[str]) -> Optional[str]:
    """在 df.columns 中按顺序找第一个存在的列名；找不到返回 None。"""
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _to_float(v) -> Optional[float]:
    """把百分号/千位分隔等字符串安全转换为 float；失败返回 None。"""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace(",", "")
    if s.endswith("%"):
        s = s[:-1]
    try:
        return float(s)
    except Exception:
        return None


# ---------- 实时快照（个股） ----------

def get_realtime_quotes(codes: List[str]) -> pd.DataFrame:
    """
    获取 codes 中个股的快照数据：
      返回列：code, name, price, pct_chg, amount(亿元), time
    - 优先用 ak.stock_zh_a_spot()；失败再尝试 ak.stock_zh_a_spot_em()（若存在）
    - 失败时返回空 DataFrame（避免上层中断）
    """
    df = None

    # 主接口：全市场快照
    for _ in range(3):
        try:
            df = ak.stock_zh_a_spot()
            break
        except Exception:
            time.sleep(1.2)

    # 备用接口：部分版本存在
    if df is None:
        alt = getattr(ak, "stock_zh_a_spot_em", None)
        if callable(alt):
            for _ in range(2):
                try:
                    df = alt()
                    break
                except Exception:
                    time.sleep(1.2)

    # 任何情况下，失败返回空表
    if df is None or df.empty:
        return pd.DataFrame(columns=["code", "name", "price", "pct_chg", "amount", "time"])

    # 列名自适配
    code_col = _pick_col(df, ["代码", "symbol", "证券代码"])
    name_col = _pick_col(df, ["名称", "name", "证券简称"])
    price_col = _pick_col(df, ["最新价", "最新价(元)", "最新", "现价"])
    pct_col = _pick_col(df, ["涨跌幅", "涨跌幅(%)", "涨跌幅 %", "涨幅"])
    amt_col = _pick_col(df, ["成交额", "成交额(元)", "成交额(万元)", "成交额(亿元)"])

    if not all([code_col, name_col, price_col, pct_col, amt_col]):
        # 列名不齐，返回空表以免上层出错
        return pd.DataFrame(columns=["code", "name", "price", "pct_chg", "amount", "time"])

    # 统一前缀，过滤所需 codes
    df[code_col] = df[code_col].astype(str).str.lower()
    wanted = set(_norm_code(c) for c in codes)
    # 有的接口返回不带前缀：这里补一次
    df["prefixed"] = df[code_col].apply(_norm_code)
    df = df[df["prefixed"].isin(wanted)].copy()

    if df.empty:
        return pd.DataFrame(columns=["code", "name", "price", "pct_chg", "amount", "time"])

    # 成交额统一转为“亿元”
    amt_name = amt_col or ""
    amt_series = df[amt_col].apply(_to_float)
    if "亿元" in amt_name:
        amount_yi = amt_series
    elif "万元" in amt_name:
        # 万元 -> 亿元： 除以 100
        amount_yi = amt_series.apply(lambda x: None if x is None else x / 100.0)
    else:
        # 视为 元 -> 亿元： 除以 1e8
        amount_yi = amt_series.apply(lambda x: None if x is None else x / 1e8)

    out = pd.DataFrame({
        "code": df["prefixed"],
        "name": df[name_col],
        "price": df[price_col].apply(_to_float),
        "pct_chg": df[pct_col].apply(_to_float),
        "amount": amount_yi.round(2),
        "time": pd.Timestamp.now(tz="Asia/Shanghai").strftime("%Y-%m-%d %H:%M:%S"),
    })
    return out


# ---------- 个股当日资金流（主力/超大/大/中/小 单） ----------

def get_individual_moneyflow(code: str) -> Dict[str, Optional[float]]:
    """
    获取单只个股当日资金净流入（万元）的最新一条：
      返回键：main, super, large, medium, small, ts
    - 优先调用 ak.stock_individual_fund_flow(stock='代码不带前缀')
    - 失败返回各项 None（由上层做展示兜底）
    """
    pure = _norm_code(code)[2:]  # 去掉 sh/sz 前缀
    try:
        df = ak.stock_individual_fund_flow(stock=pure)
        if df is None or df.empty:
            raise RuntimeError("empty dataframe")
        last = df.iloc[-1]

        # 常见列名：主力净流入 / 超大单净流入 / 大单净流入 / 中单净流入 / 小单净流入 / 时间
        def gv(col):
            return _to_float(last.get(col))

        return {
            "main": gv("主力净流入"),
            "super": gv("超大单净流入"),
            "large": gv("大单净流入"),
            "medium": gv("中单净流入"),
            "small": gv("小单净流入"),
            "ts": str(last.get("时间", "")),
        }
    except Exception:
        return {"main": None, "super": None, "large": None, "medium": None, "small": None, "ts": ""}


# ---------- 北向资金概览（沪股通/深股通/合计，当日净流入，单位：亿元） ----------

def get_northbound_overview() -> Dict[str, Optional[float]]:
    """
    使用 ak.stock_hsgt_fund_flow_summary_em() 读取北向资金当日净流入（亿元）。
    - 兼容不同版本列名（通过候选列名表）
    - 取“最新一行”（若有“日期”列会先按日期排序）
    - 失败时返回各项 None（由上层 RSS 心跳条目兜底）
    返回：
      {"sh": float|None, "sz": float|None, "total": float|None, "time": "YYYY-MM-DD HH:MM:SS"}
    """
    try:
        df = ak.stock_hsgt_fund_flow_summary_em()
        if df is None or df.empty:
            raise RuntimeError("empty dataframe")

        # 取最新一行
        if "日期" in df.columns:
            try:
                df["日期"] = pd.to_datetime(df["日期"])
                row = df.sort_values("日期").iloc[-1]
            except Exception:
                row = df.iloc[0]
        else:
            row = df.iloc[0]

        # 版本兼容：候选列名
        col_map = {
            "sh": ["沪股通-净流入", "沪股通净流入", "当日资金净流入-沪股通", "沪股通-当日资金净流入"],
            "sz": ["深股通-净流入", "深股通净流入", "当日资金净流入-深股通", "深股通-当日资金净流入"],
            "total": ["北向资金-净流入", "北向资金净流入", "当日资金净流入-北向", "北向资金-当日资金净流入"],
        }

        out = {}
        for k, cands in col_map.items():
            val = None
            for c in cands:
                if c in row:
                    val = _to_float(row[c])
                    if val is not None:
                        break
            out[k] = round(val, 2) if val is not None else None

        out["time"] = pd.Timestamp.now(tz="Asia/Shanghai").strftime("%Y-%m-%d %H:%M:%S")
        return out

    except Exception as e:
        # 可按需 print(e) 进行调试；生产环境保持静默返回 None
        return {"sh": None, "sz": None, "total": None, "time": ""}


# （可选）导出列表，便于 from data_providers import *
__all__ = [
    "_norm_code",
    "get_realtime_quotes",
    "get_individual_moneyflow",
    "get_northbound_overview",
]
