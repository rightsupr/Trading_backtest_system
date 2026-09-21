"""学习示例：均线金叉 + 趋势、RSI、MACD、成交量与波动率过滤。

将本文件完整复制到工作台的「Python 策略代码」框，即可校验和回测。
也可以用本项目的 .venv 在 VS Code / PyCharm 中编辑和导入此文件。
这里只定义信号函数；直接执行本文件不会自动下载行情或运行回测。
18 个默认参数用于教学，未经过收益优化。
"""

import math

import pandas as pd
from app.indicators.technical import calculate_atr, calculate_macd, calculate_rsi, sma

# 编辑器「数值参数」会覆盖这里同名的默认值；没有填写时使用这里的值。
# 当前系统只接受数值参数；开关用 0 / 1，不使用字符串 "true" / "false"。
DEFAULT_PARAMS = {
    "fast_ma": 5,  # 短均线周期，单位：K 线根数
    "slow_ma": 20,  # 长均线周期
    "trend_ma": 60,  # 趋势均线：买入时收盘价须在它上方
    "macd_fast": 12,  # MACD 快 EMA 周期
    "macd_slow": 26,  # MACD 慢 EMA 周期
    "macd_signal": 9,  # MACD 的 DEA 平滑周期
    "rsi_period": 14,  # RSI 周期
    "rsi_min": 40,  # 买入 RSI 下限，RSI 的单位是 0~100
    "rsi_max": 75,  # 买入 RSI 上限
    "exit_rsi": 35,  # 持仓时 RSI 低于此值，发出卖出信号
    "volume_period": 20,  # 计算昨日及之前的平均成交量
    "volume_ratio_min": 0.8,  # 今日量 / 此前平均量，至少为 0.8 倍
    "atr_period": 14,  # ATR 周期
    "atr_ratio_max": 0.10,  # ATR / 收盘价上限；0.10 表示 10%
    "max_signal_bars": 30,  # 距买入信号最多经过多少根 K 线后发出卖出
    "cooldown_bars": 3,  # 卖出信号之后，跳过几根 K 线的买入机会
    "use_macd_filter": 1,  # 1=买入要求 DIF > DEA；0=不要求
    "use_volume_filter": 1,  # 1=启用成交量过滤；0=不要求
}


def generate_signals(data, params):
    """输入整段历史行情，返回与行情逐行对应的四列 DataFrame。

    data: 按日期从早到晚排列的单只股票日线及系统指标。
    params: 编辑器传来的数值字典。资金、费率属于撮合配置，不在这里。
    target: 策略的目标仓位，0=空仓、1=满仓；不是账户实际持仓。
    """
    # ---------- 1. 合并并检查参数 ----------
    unknown = set(params) - set(DEFAULT_PARAMS)
    if unknown:
        raise ValueError(f"请删除本示例未使用的参数：{', '.join(sorted(unknown))}")
    p = {**DEFAULT_PARAMS, **params}
    for key, value in p.items():
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{key} 必须是有限数值")

    # 不把 5.8 天静默变成 5 天，避免参数含义与界面显示不一致。
    periods = [
        "fast_ma",
        "slow_ma",
        "trend_ma",
        "macd_fast",
        "macd_slow",
        "macd_signal",
        "rsi_period",
        "volume_period",
        "atr_period",
        "max_signal_bars",
    ]
    for key in periods + ["cooldown_bars"]:
        minimum = 0 if key == "cooldown_bars" else 1
        if p[key] != int(p[key]) or p[key] < minimum:
            raise ValueError(f"{key} 必须是 >= {minimum} 的整数")
        p[key] = int(p[key])
    if not p["fast_ma"] < p["slow_ma"] <= p["trend_ma"]:
        raise ValueError("周期必须满足 fast_ma < slow_ma <= trend_ma")
    if not p["macd_fast"] < p["macd_slow"]:
        raise ValueError("macd_fast 必须小于 macd_slow")
    if not 0 <= p["exit_rsi"] < p["rsi_min"] < p["rsi_max"] <= 100:
        raise ValueError("必须满足 0 <= exit_rsi < rsi_min < rsi_max <= 100")
    if p["volume_ratio_min"] < 0 or p["atr_ratio_max"] <= 0:
        raise ValueError("volume_ratio_min 必须非负，atr_ratio_max 必须为正")
    for key in ["use_macd_filter", "use_volume_filter"]:
        if p[key] not in (0, 1):
            raise ValueError(f"{key} 只能使用 0 或 1")

    # ---------- 2. 按自己的参数计算指标 ----------
    # 系统已提供默认指标；这里重新计算，确保 params 真正控制所用指标。
    d = data.copy().reset_index(drop=True)
    d = calculate_macd(d, p["macd_fast"], p["macd_slow"], p["macd_signal"])
    d = calculate_rsi(d, p["rsi_period"])
    d = calculate_atr(d, p["atr_period"])
    fast = sma(d["close"], p["fast_ma"])
    slow = sma(d["close"], p["slow_ma"])
    trend = sma(d["close"], p["trend_ma"])

    # shift(1) 表示昨日：此处均量不包含今天，只有过去的成交量。
    previous_volume = sma(d["volume"], p["volume_period"]).shift(1)
    volume_ratio = d["volume"] / previous_volume.where(previous_volume > 0)
    atr_ratio = d["atr"] / d["close"].where(d["close"] > 0)

    # ---------- 3. 写你的买卖条件：通常主要修改这一段 ----------
    cross_up = (fast > slow) & (fast.shift(1) <= slow.shift(1))
    cross_down = (fast < slow) & (fast.shift(1) >= slow.shift(1))
    buy = (
        cross_up  # 今日短均线上穿长均线
        & (d["close"] > trend)  # 位于趋势均线上方
        & d["rsi"].between(p["rsi_min"], p["rsi_max"])
        & (atr_ratio <= p["atr_ratio_max"])  # 波动率没有过高
        & (d["volume"] > 0)  # 当天有成交量
    )
    if p["use_macd_filter"]:
        buy &= d["macd_dif"] > d["macd_dea"]
    if p["use_volume_filter"]:
        buy &= volume_ratio >= p["volume_ratio_min"]

    # 指标刚开始不足若干根数据时会出现 NaN，需要等待预热。
    ready = (
        pd.concat([fast, slow, trend, d["rsi"], atr_ratio], axis=1).notna().all(axis=1)
    )
    if p["use_macd_filter"]:
        ready &= d[["macd_dif", "macd_dea"]].notna().all(axis=1)
    if p["use_volume_filter"]:
        ready &= volume_ratio.notna()

    # ---------- 4. 从条件生成逐日状态，不能只返回有买卖的几天 ----------
    rows = []
    target = 0
    entry_signal_index = None
    last_exit_index = None
    for i, day in enumerate(d["date"]):
        action = "HOLD" if target else "NONE"
        reason = "保持目标持仓" if target else "等待买入条件"

        if target:
            # 这是自买入信号以来的 K 线数，不是实际成交后的持仓天数。
            age = i - entry_signal_index
            exits = []
            if cross_down.iloc[i]:
                exits.append("短均线下穿长均线")
            if d["close"].iloc[i] < trend.iloc[i]:
                exits.append("收盘价跌破趋势均线")
            if d["rsi"].iloc[i] < p["exit_rsi"]:
                exits.append(f"RSI 低于 {p['exit_rsi']:g}")
            if age >= p["max_signal_bars"]:
                exits.append(f"距买入信号已经 {age} 根 K 线")
            if exits:
                action, target, reason = "SELL", 0, "；".join(exits)
                last_exit_index = i
                entry_signal_index = None
        elif last_exit_index is not None and i - last_exit_index <= p["cooldown_bars"]:
            reason = "卖出信号后的冷却期，暂不买入"
        elif not ready.iloc[i]:
            reason = "指标预热或所需数据缺失，暂不买入"
        elif buy.iloc[i]:
            action, target = "BUY", 1
            entry_signal_index = i
            reason = (
                f"MA{p['fast_ma']} 上穿 MA{p['slow_ma']}，价格位于 MA{p['trend_ma']} 上方；"
                f"RSI={d['rsi'].iloc[i]:.1f}，ATR/价格={atr_ratio.iloc[i]:.2%}"
            )
            if p["use_macd_filter"]:
                reason += "；DIF > DEA"
            if p["use_volume_filter"]:
                reason += f"；相对前期均量={volume_ratio.iloc[i]:.2f} 倍"
        rows.append(
            {"date": day, "signal": action, "position_target": target, "reason": reason}
        )

    # 四个字段名固定；日期、行数、顺序必须与输入完全一致。
    return pd.DataFrame(rows, columns=["date", "signal", "position_target", "reason"])
