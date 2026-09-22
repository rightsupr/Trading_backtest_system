"""000938 波段启动观察 V2：短期动量转强 + 小平台突破。

目标是定位可能的上涨启动点，不承诺买到最低价，也不要求持有固定天数。
研究候选：以当日完整日线近似尾盘信号，系统默认按当日收盘价加减滑点尝试成交。
完整复制此文件到 Python 编辑器即可。策略没有真实账户或成交回调。
"""

import math

import pandas as pd
from app.indicators.technical import calculate_atr, ema

DEFAULT_PARAMS = {
    "momentum_ema": 5,  # 短期动量
    "trend_ema": 20,  # 波段趋势
    "trend_slope": 3,  # 趋势 EMA 比几根之前高
    "breakout_period": 5,  # 收盘突破此前 5 根最高价，确认小平台突破
    "atr_period": 14,
    "max_entry_atr": 2.0,  # 收盘距趋势 EMA 最多 2 个 ATR，避免价格偏离过大
    "trailing_atr": 3.0,  # 信号以来最高收盘下方 3 ATR 的只升不降跟随线
    "exit_confirm": 2,  # 连续 2 根收盘跌破趋势 EMA 退出
    "cooldown_bars": 3,  # 卖出信号后跳过 3 根 K 线，避免立即重入
}


def generate_signals(data, params):
    """输入行情和数值参数，返回逐日四列信号表。"""
    unknown = set(params) - set(DEFAULT_PARAMS)
    if unknown:
        raise ValueError(f"请删除旧策略参数：{', '.join(sorted(unknown))}")
    p = {**DEFAULT_PARAMS, **params}
    for key, value in p.items():
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{key} 必须为有限数值")
    for key in [
        "momentum_ema",
        "trend_ema",
        "trend_slope",
        "breakout_period",
        "atr_period",
        "exit_confirm",
        "cooldown_bars",
    ]:
        minimum = 0 if key == "cooldown_bars" else 1
        if p[key] != int(p[key]) or p[key] < minimum:
            raise ValueError(f"{key} 必须是 >= {minimum} 的整数")
        p[key] = int(p[key])
    if p["momentum_ema"] >= p["trend_ema"]:
        raise ValueError("momentum_ema 必须小于 trend_ema")
    if p["max_entry_atr"] <= 0 or p["trailing_atr"] <= 0:
        raise ValueError("ATR 倍数必须为正")

    d = calculate_atr(data.copy().reset_index(drop=True), p["atr_period"])
    close, high, volume, atr = d["close"], d["high"], d["volume"], d["atr"]
    momentum = ema(close, p["momentum_ema"])
    trend = ema(close, p["trend_ema"])
    # 排除今天，避免把尚未发生的价格或当天高点放入突破基准。
    platform = high.rolling(p["breakout_period"]).max().shift(1)
    extension = (close - trend) / atr.where(atr > 0)
    ready = (
        pd.concat([momentum, trend.shift(p["trend_slope"]), platform, atr], axis=1)
        .notna()
        .all(axis=1)
    )
    ready &= atr > 0

    # 买点：短期动量强于波段趋势、趋势已经向上、小平台被收盘突破。
    # 不要求 EMA60 已经向上；不使用 RSI 超买过滤，以免屏蔽启动行情。
    buy = (
        (momentum > trend)
        & (trend > trend.shift(p["trend_slope"]))
        & (close > platform)
        & (close > trend)
        & (extension <= p["max_entry_atr"])
        & (volume > 0)
    )
    below_trend = (close < trend).astype(int).rolling(p["exit_confirm"]).sum() >= p[
        "exit_confirm"
    ]
    rows, target = [], 0
    last_exit = None
    peak_close = None
    trailing_line = None
    for i, day in enumerate(d["date"]):
        price = close.iloc[i]
        action, reason = (
            ("HOLD", "持有上涨波段，等待退出条件")
            if target
            else ("NONE", "等待短期动量转强并突破小平台")
        )
        if target:
            peak_close = max(peak_close, price)
            trailing_line = max(
                trailing_line, peak_close - p["trailing_atr"] * atr.iloc[i]
            )
            exits = []
            if price <= trailing_line:
                exits.append(f"收盘跌至信号 ATR 跟随线 {trailing_line:.2f} 以下")
            if below_trend.iloc[i]:
                exits.append(f"连续 {p['exit_confirm']} 根收盘跌破 EMA{p['trend_ema']}")
            if exits:
                action, target, reason = "SELL", 0, "；".join(exits)
                last_exit, peak_close, trailing_line = i, None, None
        elif not ready.iloc[i]:
            reason = "指标预热或所需数据缺失，暂不买入"
        elif last_exit is not None and i - last_exit <= p["cooldown_bars"]:
            reason = "退出后的冷却期"
        elif buy.iloc[i]:
            action, target = "BUY", 1
            peak_close = price
            trailing_line = price - p["trailing_atr"] * atr.iloc[i]
            reason = (
                f"EMA{p['momentum_ema']} > EMA{p['trend_ema']}，后者向上；"
                f"收盘突破此前 {p['breakout_period']} 根最高价 {platform.iloc[i]:.2f}；"
                f"偏离趋势线 {extension.iloc[i]:.2f} ATR；初始信号跟随线 {trailing_line:.2f}"
            )
        rows.append(
            {"date": day, "signal": action, "position_target": target, "reason": reason}
        )
    return pd.DataFrame(rows, columns=["date", "signal", "position_target", "reason"])
