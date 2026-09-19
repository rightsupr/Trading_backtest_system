from textwrap import dedent

PYTHON_EXAMPLES = [
    {
        "id": "ma_cross",
        "name": "Python 均线金叉",
        "description": "短均线上穿长均线买入，下穿卖出。只需修改参数或条件，保留函数入口与返回字段。",
        "parameters": {"fast_ma": 5, "slow_ma": 20},
        "code": dedent('''\
            import pandas as pd
            from app.indicators.technical import sma

            def generate_signals(data, params):
                """data 按日期递增；输出逐日信号，系统负责次日开盘成交。"""
                fast = int(params.get("fast_ma", 5))
                slow = int(params.get("slow_ma", 20))
                if not 0 < fast < slow:
                    raise ValueError("必须满足 0 < fast_ma < slow_ma")

                # 1. 使用系统指标，也可以用 pandas 编写自己的因果指标。
                short_ma = sma(data["close"], fast)
                long_ma = sma(data["close"], slow)

                # 2. 主要修改这里的买卖条件。shift(1) 是上一根 K 线。
                buy = (short_ma > long_ma) & (short_ma.shift(1) <= long_ma.shift(1))
                sell = (short_ma < long_ma) & (short_ma.shift(1) >= long_ma.shift(1))

                # 3. 保留输出结构；target 是目标仓位，不是撮合后的实际持仓。
                rows, target = [], 0
                for i, day in enumerate(data["date"]):
                    action, reason = ("HOLD", "保持目标持仓") if target else ("NONE", "等待金叉")
                    if sell.iloc[i]:
                        if target:
                            action, target, reason = "SELL", 0, "短均线下穿长均线"
                    elif buy.iloc[i] and not target:
                        action, target, reason = "BUY", 1, "短均线上穿长均线"
                    rows.append({"date": day, "signal": action,
                                 "position_target": target, "reason": reason})
                return pd.DataFrame(rows)
        '''),
    },
    {
        "id": "dif_slope",
        "name": "Python DIF 斜率拐头",
        "description": "零轴下 DIF 斜率由非正转为超过阈值时买入；DIF 下穿 DEA 或斜率转弱时卖出。",
        "parameters": {"slope_period": 1, "buy_threshold": 0.05, "sell_threshold": -0.05},
        "code": dedent("""\
            import pandas as pd
            from app.indicators.technical import calculate_macd, slope

            def generate_signals(data, params):
                data = calculate_macd(data, fast=12, slow=26, signal=9)
                rate = slope(data["macd_dif"], int(params.get("slope_period", 1)))
                # 自由修改这些条件；斜率单位为价格/交易日，阈值不是百分比。
                buy = ((data["macd_dif"] < 0) & (rate.shift(1) <= 0)
                       & (rate > params.get("buy_threshold", 0.05)))
                cross_down = ((data["macd_dif"] < data["macd_dea"])
                              & (data["macd_dif"].shift(1) >= data["macd_dea"].shift(1)))
                sell = cross_down | (rate < params.get("sell_threshold", -0.05))
                rows, target = [], 0
                for i, day in enumerate(data["date"]):
                    action, reason = ("HOLD", "保持目标持仓") if target else ("NONE", "等待 DIF 拐头")
                    if sell.iloc[i]:
                        if target:
                            action, target, reason = "SELL", 0, "DIF 下穿 DEA 或斜率转弱"
                    elif buy.iloc[i] and not target:
                        action, target, reason = "BUY", 1, f"零轴下 DIF 斜率拐头：{rate.iloc[i]:.4f}"
                    rows.append({"date": day, "signal": action,
                                 "position_target": target, "reason": reason})
                return pd.DataFrame(rows)
        """),
    },
]
