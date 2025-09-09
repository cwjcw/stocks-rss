# 我的A股盯盘RSS

> 实时查看 **涨跌**、**北向资金**、**主力/超大/大/中/小单净流入**，输出为 **RSS** 订阅源，可被 Folo / Inoreader / Tiny Tiny RSS 等阅读器订阅。基于 **AKShare** 实现。

## 功能
- 自定义股票清单
- 实时快照（最新价、涨跌幅、成交额）
- 个股当日资金净流入（主力/超大/大/中/小单）
- 北向资金当日净流入（沪股通/深股通/合计）
- 输出 RSS（XML）

## 快速开始

```bash
pip install -r requirements.txt
python src/main.py
# RSS 文件默认输出到 public/a-shares.xml
