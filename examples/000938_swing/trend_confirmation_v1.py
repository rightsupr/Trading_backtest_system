"""000938 上涨波段 V1：趋势过滤 + 突破/回踩恢复 + 趋势退出。

固定参数的研究候选，不根据某一段历史收益自动挑选参数。
整份文件可直接粘贴到 Python 编辑器。默认参数无需逐一添加到面板。
目标状态不是实际账户；ATR 跟随线按信号计算，尾盘信号触发、默认按当日收盘价加减滑点尝试退出。
"""

import math

import pandas as pd
from app.indicators.technical import calculate_atr, ema, sma

DEFAULT_PARAMS = {
    "trend_fast": 20,  # 波段趋势：20 日 EMA
    "trend_slow": 60,  # 较长趋势：60 日 EMA
    "trend_slope": 5,  # 长 EMA 比 5 根之前高，才允许新买入
    "breakout_period": 20,  # 收盘突破此前 20 根最高价
    "volume_period": 20,  # 突破量与此前 20 根均量比较
    "breakout_volume_ratio": 1.2,  # 突破要求至少 1.2 倍均量
    "atr_period": 14,  # 波动率窗口
    "max_entry_atr": 2.0,  # 入场收盘偏离短 EMA 不超过 2 个 ATR
    "trailing_atr": 3.0,  # 信号以来最高收盘价下方 3 个 ATR 的跟随线
    "exit_confirm": 2,  # 连续 2 根收盘跌破短 EMA 退出
    "cooldown_bars": 3,  # 卖出信号之后跳过 3 根 K 线
    "enable_pullback": 1,  # 1 启用回踩恢复买入；0 仅保留突破买入
}


def generate_signals(data, params):
    """逐日输出 date、signal、position_target、reason；只使用当日及过去行情。"""
    unknown = set(params) - set(DEFAULT_PARAMS)
    if unknown:
        raise ValueError(f"请删除旧策略的无关参数：{', '.join(sorted(unknown))}")
    p = {**DEFAULT_PARAMS, **params}
    for key, value in p.items():
        if not isinstance(value, (float, int)) or not math.isfinite(value):
            raise ValueError(f"{key} 必须是有限数值")
    periods = [
        "trend_fast",
        "trend_slow",
        "trend_slope",
        "breakout_period",
        "volume_period",
        "atr_period",
        "exit_confirm",
        "cooldown_bars",
    ]
    for key in periods:
        minimum = 0 if key == "cooldown_bars" else 1
        if p[key] != int(p[key]) or p[key] < minimum:
            raise ValueError(f"{key} 必须是 >= {minimum} 的整数")
        p[key] = int(p[key])
    if p["trend_fast"] >= p["trend_slow"]:
        raise ValueError("trend_fast 必须小于 trend_slow")
    for key in ["breakout_volume_ratio", "max_entry_atr", "trailing_atr"]:
        if p[key] <= 0:
            raise ValueError(f"{key} 必须为正数")
    if p["enable_pullback"] not in (0, 1):
        raise ValueError("enable_pullback 只能为 0 或 1")

    # 1. 波段趋势与波动率。预热使用所选区间内的历史，最初不足时不买入。
    d = calculate_atr(data.copy().reset_index(drop=True), p["atr_period"])
    close, high, volume = d["close"], d["high"], d["volume"]
    fast = ema(close, p["trend_fast"])
    slow = ema(close, p["trend_slow"])
    previous_high = high.rolling(p["breakout_period"]).max().shift(1)
    previous_volume = sma(volume, p["volume_period"]).shift(1)
    trend = (fast > slow) & (slow > slow.shift(p["trend_slope"]))
    extension = (close - fast) / d["atr"].where(d["atr"] > 0)
    entry_zone = (close > fast) & (extension <= p["max_entry_atr"])

    # 2A. 突破买入：不把今天的最高价包含在被突破的历史高点里。
    breakout = (
        (close > previous_high)
        & (previous_volume > 0)
        & (volume >= p["breakout_volume_ratio"] * previous_volume)
    )
    # 2B. 回踩恢复：昨日收盘在短 EMA 下方但仍在长 EMA 上方，
    # 今日重新站回短 EMA，并收在昨日最高价上方。不要求回踩买入也放量。
    pullback = (
        (close.shift(1) <= fast.shift(1))
        & (close.shift(1) >= slow.shift(1))
        & (close > fast)
        & (close > high.shift(1))
    )
    below_fast = (close < fast).astype(int).rolling(p["exit_confirm"]).sum() >= p[
        "exit_confirm"
    ]
    ready = (
        pd.concat([fast, slow.shift(p["trend_slope"]), d["atr"]], axis=1)
        .notna()
        .all(axis=1)
    )
    ready &= d["atr"] > 0

    # 3. 信号状态。没有固定止盈和持有天数上限，趋势延续就继续持有。
    rows, target = [], 0
    last_exit = None
    peak_close = None
    trailing_line = None
    for i, day in enumerate(d["date"]):
        price, atr = close.iloc[i], d["atr"].iloc[i]
        action, reason = (
            ("HOLD", "上涨波段持有，等待退出条件")
            if target
            else ("NONE", "等待上涨趋势和入场机会")
        )
        if target:
            # 只升不降，不能因 ATR 变大而把跟随线重新放低。
            peak_close = max(peak_close, price)
            trailing_line = max(trailing_line, peak_close - p["trailing_atr"] * atr)
            exits = []
            if price <= trailing_line:
                exits.append(f"收盘跌至 ATR 跟随线 {trailing_line:.2f} 以下")
            if below_fast.iloc[i]:
                exits.append(
                    f"连续 {p['exit_confirm']} 根收盘低于 EMA{p['trend_fast']}"
                )
            if price < slow.iloc[i]:
                exits.append(f"收盘跌破 EMA{p['trend_slow']}")
            if exits:
                action, target, reason = "SELL", 0, "；".join(exits)
                last_exit, peak_close, trailing_line = i, None, None
        elif not ready.iloc[i]:
            reason = "趋势指标预热或 ATR 不可用，等待"
        elif last_exit is not None and i - last_exit <= p["cooldown_bars"]:
            reason = "退出后的冷却期"
        elif not trend.iloc[i]:
            reason = "短 EMA 未高于长 EMA，或长 EMA 尚未上升"
        elif not entry_zone.iloc[i]:
            reason = "价格未站上短 EMA，或偏离过大，等待合适入场位置"
        elif volume.iloc[i] > 0 and (
            breakout.iloc[i] or (p["enable_pullback"] and pullback.iloc[i])
        ):
            action, target = "BUY", 1
            peak_close = price
            trailing_line = price - p["trailing_atr"] * atr
            if breakout.iloc[i]:
                reason = f"上涨趋势中突破此前 {p['breakout_period']} 根高点；量比={volume.iloc[i] / previous_volume.iloc[i]:.2f}"
            else:
                reason = f"上涨趋势回踩后重回 EMA{p['trend_fast']}，并收于昨日高点上方"
            reason += f"；偏离短 EMA={extension.iloc[i]:.2f} ATR；初始信号跟随线={trailing_line:.2f}"
        rows.append(
            {"date": day, "signal": action, "position_target": target, "reason": reason}
        )
    return pd.DataFrame(rows, columns=["date", "signal", "position_target", "reason"])
