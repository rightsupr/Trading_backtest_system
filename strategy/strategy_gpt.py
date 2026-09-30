"""000938 波段启动 V2：日内峰值保护，优先控制利润回吐。

目标是定位可能的上涨启动点，不承诺买到最低价，也不要求持有固定天数。
研究候选：以当日完整日线近似尾盘信号，系统默认按当日收盘价加减滑点尝试成交。
完整复制此文件到 Python 编辑器即可。策略没有真实账户或成交回调。
"""

import math

import pandas as pd
from app.indicators.technical import calculate_atr, ema

BASE_PARAMS = {
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


def _baseline_signals(data, params):
    """输入行情和数值参数，返回逐日四列信号表。"""
    unknown = set(params) - set(BASE_PARAMS)
    if unknown:
        raise ValueError(f"请删除旧策略参数：{', '.join(sorted(unknown))}")
    p = {**BASE_PARAMS, **params}
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


# 百分比用小数表示。阈值按信号价格计算，不是账户实际成本或保证成交价。
DEFAULT_PARAMS = {
    **BASE_PARAMS,
    "initial_stop_pct": 0.05,  # 入场信号价格下方 5% 的初始风险线
    "profit_arm_atr": 2.0,
    "profit_arm_pct": 0.04,  # 上涨 2 个入场 ATR 或 4%，先到者激活
    "profit_trailing_atr": 1.5,
    "max_giveback_pct": 0.05,  # 激活后：持仓峰值下方最多 5% 的触发距离
    "breakeven_arm_pct": 0.06,
    "breakeven_floor_pct": 0.005,  # 仅为费用缓冲，不保证交易净盈利
    "profit_lock_arm_pct": 0.10,
    "profit_keep_ratio": 0.60,  # 上涨达到 10% 后，保留峰值浮盈的 60%
    "weakness_exit": 0,  # 走弱退出对照明显卖早，默认关闭
    "peak_reference": 1,  # 1：买入后日内最高价；0：最高收盘，仅供研究对照
}


def generate_signals(data, params):
    """原买点 + 分阶段保护，输出保护线；仅在收盘触发，不模拟盘中止损成交。"""
    unknown = set(params) - set(DEFAULT_PARAMS)
    if unknown:
        raise ValueError(f"未知策略参数：{', '.join(sorted(unknown))}")
    p = {**DEFAULT_PARAMS, **params}
    for key, value in p.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"{key} 必须为有限数值")
    for key in [
        "initial_stop_pct",
        "profit_arm_pct",
        "max_giveback_pct",
        "breakeven_arm_pct",
        "profit_lock_arm_pct",
        "profit_keep_ratio",
    ]:
        if not 0 < p[key] < 1:
            raise ValueError(f"{key} 必须在 0 和 1 之间，百分比用小数表示")
    if not 0 <= p["breakeven_floor_pct"] < p["breakeven_arm_pct"]:
        raise ValueError("费用缓冲必须非负且小于保本激活涨幅")
    if not p["profit_arm_pct"] <= p["breakeven_arm_pct"] <= p["profit_lock_arm_pct"]:
        raise ValueError("保护、保本、利润保留激活涨幅必须依次递增")
    if (
        p["profit_arm_atr"] <= 0
        or not 0 < p["profit_trailing_atr"] <= p["trailing_atr"]
    ):
        raise ValueError("保护 ATR 倍数必须为正，跟随距离不得超过原始距离")
    if p["weakness_exit"] not in (0, 1):
        raise ValueError("weakness_exit 只能为 0 或 1")
    if p["peak_reference"] not in (0, 1):
        raise ValueError("peak_reference 只能为 0 或 1")

    baseline = _baseline_signals(data, {k: p[k] for k in BASE_PARAMS})
    d = calculate_atr(data.copy().reset_index(drop=True), int(p["atr_period"]))
    fast = ema(d.close, int(p["momentum_ema"]))
    prior_low = d.low.rolling(2).min().shift(1)
    rows, target = [], 0
    entry_price = entry_atr = peak_price = protection_line = None
    line_source, armed = "", False
    peak_label = "持仓最高价" if p["peak_reference"] else "最高收盘"
    for i, day in enumerate(d.date):
        price, atr = float(d.close.iloc[i]), float(d.atr.iloc[i])
        original = baseline.iloc[i]
        action, reason = (
            ("HOLD", "趋势持有") if target else ("NONE", "等待原策略下个买点")
        )
        plotted_line = float("nan")
        if target:
            # 此时是收盘决策，当日高点已知；买入当日走 BUY 分支，不使用其高点。
            peak_price = max(
                peak_price, float(d.high.iloc[i]) if p["peak_reference"] else price
            )
            peak_gain = peak_price / entry_price - 1
            arm_distance = min(
                p["profit_arm_atr"] * entry_atr, p["profit_arm_pct"] * entry_price
            )
            armed = armed or peak_price - entry_price >= arm_distance
            candidates = [(entry_price * (1 - p["initial_stop_pct"]), "初始风险")]
            if armed:
                candidates.extend(
                    [
                        (peak_price - p["profit_trailing_atr"] * atr, "ATR 跟随"),
                        (peak_price * (1 - p["max_giveback_pct"]), "回吐比例"),
                    ]
                )
            if peak_gain >= p["breakeven_arm_pct"]:
                candidates.append(
                    (entry_price * (1 + p["breakeven_floor_pct"]), "费用缓冲")
                )
            if peak_gain >= p["profit_lock_arm_pct"]:
                candidates.append(
                    (
                        entry_price
                        + p["profit_keep_ratio"] * (peak_price - entry_price),
                        "利润保留",
                    )
                )
            next_line, next_source = max(candidates, key=lambda item: item[0])
            if next_line > protection_line:
                protection_line, line_source = next_line, next_source
            plotted_line = protection_line
            exits = []
            if price <= protection_line:
                exits.append(
                    f"{line_source}保护：收盘 {price:.2f} 跌至保护线 {protection_line:.2f} 以下"
                )
            if (
                p["weakness_exit"]
                and armed
                and price < fast.iloc[i]
                and price < prior_low.iloc[i]
            ):
                exits.append(
                    f"短期走弱：收盘低于 EMA{p['momentum_ema']}，并跌破此前两日最低价 {prior_low.iloc[i]:.2f}"
                )
            if original.signal == "SELL":
                exits.append(original.reason)
            if exits:
                giveback = 1 - price / peak_price
                action, target = "SELL", 0
                reason = (
                    "；".join(exits)
                    + f"；{peak_label} {peak_price:.2f}，至收盘回吐 {giveback:.2%}；按撮合价成交"
                )
                entry_price = entry_atr = peak_price = protection_line = None
                line_source, armed = "", False
            else:
                reason = f"{'保护已激活' if armed else '初始风控'}，{line_source}保护线 {protection_line:.2f}，{peak_label} {peak_price:.2f}"
        elif original.signal == "BUY":
            action, target = "BUY", 1
            entry_price, entry_atr, peak_price = price, atr, price
            protection_line = price * (1 - p["initial_stop_pct"])
            line_source, armed = "初始风险", False
            plotted_line = protection_line
            # 不将买入收盘之前的日内高点当成买后盈利。
            reason = (
                original.reason
                + f"；初始风险线 {protection_line:.2f}（信号价下方 {p['initial_stop_pct']:.1%}）"
            )
        elif original.position_target == 1:
            reason = "已保护退出，等待原策略本轮结束；本版本仅调整退出"
        rows.append(
            {
                "date": day,
                "signal": action,
                "position_target": target,
                "reason": reason,
                "plot_protection": plotted_line,
            }
        )
    result = pd.DataFrame(
        rows, columns=["date", "signal", "position_target", "reason", "plot_protection"]
    )
    result.attrs["plots"] = [
        {
            "column": "plot_protection",
            "label": "收盘退出保护线",
            "pane": "price",
            "color": "#b36bdb",
        }
    ]
    return result
