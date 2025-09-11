import tushare as ts
import pandas as pd

# 设置token（替换为你的实际token）
ts.set_token('0c1ee6d6473ee20d85144b8fd4f8f5cf6a3fd0d505fc09b029546134')
pro = ts.pro_api()

# 1. 获取北向资金当日实时数据（免费用户可能无权限，可改用历史数据）
try:
    # 沪股通实时资金流向
    sh = pro.hsgt_top10(trade_date='', ts_code='', market_type='1')  # 1=沪股通
    # 深股通实时资金流向
    sz = pro.hsgt_top10(trade_date='', ts_code='', market_type='2')  # 2=深股通
    print("沪股通实时数据：")
    print(sh)
    print("\n深股通实时数据：")
    print(sz)
except Exception as e:
    print("实时数据获取失败（可能权限不足）：", e)

# 2. 获取北向资金历史数据（推荐，免费用户可用）
# 获取最近30天的北向资金净流入数据
df = pro.moneyflow_hsgt(start_date='20230101', end_date='20231231')
# 数据说明：
# hsgt_net：北向资金净流入（亿）
# sh_net：沪股通净流入（亿）
# sz_net：深股通净流入（亿）
print("\n北向资金历史数据：")
print(df.sort_values('trade_date', ascending=False))  # 按日期倒序排列
