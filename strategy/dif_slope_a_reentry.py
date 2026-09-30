"""DIF 斜率：纯 A 入口 + 同波段再入场补丁。

enable_a_reentry=0 保持原纯 A；=1 在完成 A 交易后允许零轴上方回落再转强。
=2 保留再入场，新增持仓仅在 MA20-MA5 严格超过 reentry_ma_gap 时卖出。
=3 新增持仓采用涨速衰减、动能转负、边际递减、承接失效日线代理退出。
原 A 始终沿用原 ATR/DIF 卖出规则。零轴失效只取消新增入场资格，不强制卖出。
默认在完整日线收盘生成信号，由宿主按所选撮合口径执行。
"""

import math

import numpy as np
import pandas as pd
from app.indicators.technical import calculate_atr, calculate_macd, ema, sma

DEFAULT_PARAMS = {
    "enable_a_reentry": 1,  # 0=原纯A；1=再入场+原退出；2=MA退出；3=四逻辑退出
    "slope_bars": 2,
    "turn_window": 6,
    "entry_slope": 0.05,
    "turn_acceleration": 0.04,
    "prior_negative": 0.03,
    "exit_slope": 0.04,
    "exit_acceleration": 0.04,
    "max_extension_atr": 2.5,
    "hard_stop_atr": 2.5,
    "trail_atr": 3.0,
    "tighten_after_atr": 3.0,
    "tight_trail_atr": 2.0,
    "trailing_enabled": 1,
    "slope_exit_enabled": 1,
    "cooldown_bars": 3,
    "reentry_pullback": 0.01,  # 卖出当日或之后：DIF斜率/ATR <= -此值
    "reentry_slope": 0.02,  # 回落后转强：DIF斜率/ATR >= 此值
    "reentry_acceleration": 0.01,  # 原口径 DIF 加速度/ATR >= 此值
    "reentry_ma_gap": 0.1,  # 仅模式2：MA20-MA5严格超过此绝对价格差才退出
    "four_window": 5,  # 相邻不重叠的价格/成交量比较窗口
    "four_high_window": 10,
    "four_warning_bars": 5,  # 涨速/效率预警在持仓内的有效K线数
    "four_speed_ratio": 0.6,
    "four_effort_volume": 1.2,
    "four_efficiency_ratio": 0.5,
    "four_momentum_slope": 0.02,
    "four_confirm_bars": 2,  # 动能+预警的连续确认
    "four_momentum_bars": 3,  # 动能单独持续转负的确认
    "four_liquidity_volume": 1.5,
    "four_liquidity_range": 1.2,
    "four_close_location": 0.25,
    "four_break_buffer": 0.1,
}


def parameters(params):
    unknown = set(params) - set(DEFAULT_PARAMS)
    if unknown:
        raise ValueError(
            f"此文件只保留纯 A，请移除不支持的参数：{', '.join(sorted(unknown))}"
        )
    p = {**DEFAULT_PARAMS, **params}
    for key, value in p.items():
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError(f"{key} 必须为有限数值")
    limits = {
        "enable_a_reentry": (0, 3),
        "slope_bars": (1, 10),
        "turn_window": (2, 30),
        "cooldown_bars": (0, 30),
        "trailing_enabled": (0, 1),
        "slope_exit_enabled": (0, 1),
        "four_window": (2, 20),
        "four_high_window": (3, 40),
        "four_warning_bars": (1, 20),
        "four_confirm_bars": (1, 10),
        "four_momentum_bars": (1, 10),
    }
    for key, (low, high) in limits.items():
        if p[key] != int(p[key]) or not low <= p[key] <= high:
            raise ValueError(f"{key} 必须为 {low} 至 {high} 的整数")
        p[key] = int(p[key])
    for key in set(p) - set(limits):
        if key == "reentry_ma_gap":
            if p[key] < 0:
                raise ValueError("reentry_ma_gap 必须大于等于0")
            continue
        if not 0 < p[key] <= 20:
            raise ValueError(f"{key} 必须大于0且不超过20")
    if p["tight_trail_atr"] > p["trail_atr"]:
        raise ValueError("盈利后保护距离不能大于初始跟踪距离")
    for key in ("four_speed_ratio", "four_efficiency_ratio", "four_close_location"):
        if p[key] > 1:
            raise ValueError(f"{key} 必须大于0且不超过1")
    for key in ("four_effort_volume", "four_liquidity_volume", "four_liquidity_range"):
        if p[key] < 1:
            raise ValueError(f"{key} 必须大于等于1")
    return p


def four_logic_features(d, p):
    """四项因果量价代理；所有比较基准只使用当日或过去的数据。"""
    n = p["four_window"]
    advance = d.close - d.close.shift(n)
    previous = advance.shift(n)
    volume = d.volume.where(d.volume > 0).rolling(n).mean()
    volume_ratio = volume / volume.shift(n)
    d["four_speed_ratio"] = advance / previous.where(previous > 0)
    d["four_efficiency_ratio"] = d.four_speed_ratio / volume_ratio
    d["four_volume_growth"] = volume_ratio
    new_high = d.close > d.close.shift(1).rolling(p["four_high_window"]).max()
    d["four_raw_speed"] = (
        new_high & (advance > 0) & (previous > 0)
        & (d.four_speed_ratio <= p["four_speed_ratio"])
    ).fillna(False)
    d["four_raw_effort"] = (
        (volume_ratio >= p["four_effort_volume"])
        & (previous > 0) & (advance >= 0) & (advance < previous)
        & (d.four_efficiency_ratio <= p["four_efficiency_ratio"])
    ).fillna(False)
    d["four_price_momentum"] = (d.close - d.close.shift(3)) / d.atr.replace(0, np.nan)
    d["four_raw_momentum"] = (
        (d.plot_dif_slope <= -p["four_momentum_slope"])
        & (d.four_price_momentum < 0)
        & ((d.plot_dea_slope < 0) | (d.macd_dif < d.macd_dea))
    ).fillna(False)
    yesterday_atr = d.atr.shift(1).replace(0, np.nan)
    true_range = pd.concat(
        [d.high - d.low, (d.high - d.close.shift(1)).abs(), (d.low - d.close.shift(1)).abs()],
        axis=1,
    ).max(axis=1)
    d["four_volume_ratio"] = d.volume / d.volume.where(d.volume > 0).shift(1).rolling(20).mean()
    d["four_range_ratio"] = true_range / yesterday_atr
    d["four_close_location"] = (d.close - d.low) / (d.high - d.low).replace(0, np.nan)
    d["four_break_line"] = d.low.shift(1).rolling(5).min() - p["four_break_buffer"] * yesterday_atr
    d["four_raw_liquidity"] = (
        (d.four_volume_ratio >= p["four_liquidity_volume"])
        & (d.four_range_ratio >= p["four_liquidity_range"])
        & (d.four_close_location <= p["four_close_location"])
        & (d.close < d.open) & (d.close < d.close.shift(1))
        & (d.close < d.four_break_line)
    ).fillna(False)
    return d


def four_exit_step(row, p, state, i):
    """先累积持仓内预警，再确认；一项衰减预警本身不构成卖出。"""
    if row.four_raw_speed:
        state["speed_at"] = i
    if row.four_raw_effort:
        state["effort_at"] = i
    speed = i - state["speed_at"] < p["four_warning_bars"]
    effort = i - state["effort_at"] < p["four_warning_bars"]
    momentum, liquidity = bool(row.four_raw_momentum), bool(row.four_raw_liquidity)
    state["momentum_count"] = state["momentum_count"] + 1 if momentum else 0
    state["combo_count"] = state["combo_count"] + 1 if momentum and (speed or effort) else 0
    flags = {"four_speed": int(speed), "four_momentum": int(momentum),
             "four_effort": int(effort), "four_liquidity": int(liquidity)}
    kind = ""
    if liquidity:
        kind = "承接失效（日线代理）"
    elif state["combo_count"] >= p["four_confirm_bars"]:
        kind = "动能转负与衰减预警共振"
    elif state["momentum_count"] >= p["four_momentum_bars"]:
        kind = "动能持续转负"
    detail = (
        f"涨速预警={int(speed)}，动能负={int(momentum)}，效率预警={int(effort)}，承接代理={int(liquidity)}；"
        f"动能连续={state['momentum_count']}，共振连续={state['combo_count']}；"
        f"DIF斜率={row.plot_dif_slope:.4f}，3日推进/ATR={row.four_price_momentum:.3f}；"
        f"量比={row.four_volume_ratio:.2f}，波幅/昨ATR={row.four_range_ratio:.2f}，"
        f"收盘位置={row.four_close_location:.2f}，前低确认线={row.four_break_line:.3f}"
    )
    return kind, detail, flags


def features(data, p):
    d = calculate_macd(calculate_atr(data.copy().reset_index(drop=True), 14))
    atr = d.atr.replace(0, np.nan)
    n = p["slope_bars"]
    raw_dif = d.macd_dif.diff(n) / n
    raw_dea = d.macd_dea.diff(n) / n
    d["plot_dif_slope"] = raw_dif / atr
    d["plot_dea_slope"] = raw_dea / atr
    d["plot_acceleration"] = (raw_dif - raw_dif.shift(2)) / (2 * atr)
    d["ema5"], d["ema20"] = ema(d.close, 5), ema(d.close, 20)
    # 卖出使用图上的简单移动平均线；原入口使用的 EMA 保持原样。
    d["ma5"], d["ma20"] = sma(d.close, 5), sma(d.close, 20)
    gap = d.macd_dif - d.macd_dea
    hist_up = (gap > gap.shift(1)) & (gap.shift(1) > gap.shift(2))
    strong = d.plot_dif_slope >= p["entry_slope"]
    extension_ok = (d.close - d.ema20) / atr <= p["max_extension_atr"]
    negative_recent = (
        d.plot_dif_slope.shift(1).rolling(p["turn_window"]).min()
        <= -p["prior_negative"]
    )
    below_recent = d.macd_dif.rolling(3).min() < 0
    # 原纯 A 条件逐项保留；没有 B 或普通 MACD 金叉入口。
    d["candidate_a"] = (
        negative_recent
        & below_recent
        & (d.macd_dif <= 0.25 * atr)
        & strong
        & (d.plot_acceleration >= p["turn_acceleration"])
        & hist_up
        & (d.close > d.ema5)
        & extension_ok
    )
    positive_recent = (
        d.plot_dif_slope.shift(1).rolling(p["turn_window"]).max() >= p["entry_slope"]
    )
    d["sharp_down"] = (
        (d.plot_dif_slope <= -p["exit_slope"])
        & (d.plot_acceleration <= -p["exit_acceleration"])
        & positive_recent
        & (gap < gap.shift(1))
        & ((d.close < d.ema5) | (d.plot_dea_slope < 0))
    )
    d["persistent_down"] = (
        (d.plot_dif_slope < 0)
        & (d.plot_dif_slope.shift(1) < 0)
        & (d.plot_dea_slope < 0)
        & (d.close < d.ema5)
    )
    # 只是转强候选；还必须通过 generate_signals 中的 A 来源、窗口和回落状态检查。
    d["candidate_reentry"] = (
        (d.macd_dif >= 0)
        & (d.macd_dea >= 0)
        & (d.plot_dif_slope >= p["reentry_slope"])
        & (d.plot_acceleration >= p["reentry_acceleration"])
        & hist_up
        & (d.close > d.ema5)
        & extension_ok
    )
    return four_logic_features(d, p) if p["enable_a_reentry"] == 3 else d


def generate_signals(data, params):
    p = parameters(params)
    d = features(data, p)
    rows = []
    target, last_exit = 0, -1000
    stop = entry_close = entry_atr = peak_close = None
    mode = ""
    window_active, pullback_seen = False, False
    origin_a_date, reentry_index = None, 0
    four_state = {"speed_at": -1000, "effort_at": -1000, "momentum_count": 0, "combo_count": 0}
    for i, row in enumerate(d.itertuples()):
        action, reason = ("HOLD", "持有波段") if target else ("NONE", "等待A零轴反转")
        exit_kind, entry_kind, window_note = "", "", ""
        line = float("nan")
        four_detail = ""
        four_flags = dict.fromkeys(["four_speed", "four_momentum", "four_effort", "four_liquidity"], 0)
        valid = (
            i >= 78
            and row.atr > 0
            and row.volume > 0
            and pd.notna(row.plot_acceleration)
        )
        above_zero = (
            pd.notna(row.macd_dif)
            and pd.notna(row.macd_dea)
            and row.macd_dif >= 0
            and row.macd_dea >= 0
        )
        # 监视窗口贯穿空仓和持仓；失效后不能由 R 交易的卖出重新激活。
        if window_active and not above_zero:
            window_active, pullback_seen = False, False
            window_note = "本轮再入场资格结束：DIF或DEA跌破零轴（或数据缺失）"
        if not valid:
            reason = "78根日线预热或无成交，维持状态"
            four_state["momentum_count"] = four_state["combo_count"] = 0
            if target:
                line = stop
        elif target:
            if p["enable_a_reentry"] == 3 and mode == "A同波段再入场":
                exit_kind, four_detail, four_flags = four_exit_step(row, p, four_state, i)
                if any(four_flags.values()):
                    reason = "四逻辑观察：" + four_detail
            elif p["enable_a_reentry"] == 2 and mode == "A同波段再入场":
                gap = row.ma20 - row.ma5
                # 持仓后首次达到穿透幅度即退出；不要求穿越零差和确认同日发生。
                # 浮点误差范围内的“恰好0.1”不算严格超过0.1。
                if gap > p["reentry_ma_gap"] and not math.isclose(
                    gap, p["reentry_ma_gap"], rel_tol=0, abs_tol=1e-12
                ):
                    exit_kind = "MA5下穿MA20超过偏差"
            else:
                # 原 A 与模式1的再入场持仓保持原卖出计算。
                peak_close = max(peak_close, row.close)
                if p["trailing_enabled"]:
                    multiple = (
                        p["tight_trail_atr"]
                        if peak_close - entry_close >= p["tighten_after_atr"] * entry_atr
                        else p["trail_atr"]
                    )
                    stop = max(stop, peak_close - multiple * row.atr)
                line = stop
                if row.close <= stop:
                    exit_kind = "ATR保护"
                elif p["slope_exit_enabled"]:
                    if row.sharp_down:
                        exit_kind = "斜率强势下拐"
                    elif row.persistent_down:
                        exit_kind = "DIF持续走弱且DEA下行"
            if exit_kind:
                action, target, last_exit = "SELL", 0, i
                if p["enable_a_reentry"] == 3 and mode == "A同波段再入场":
                    reason = f"{mode}退出：{exit_kind}；{four_detail}"
                elif exit_kind == "MA5下穿MA20超过偏差":
                    reason = (
                        f"{mode}退出：{exit_kind}；MA5={row.ma5:.4f}，MA20={row.ma20:.4f}；"
                        f"MA20-MA5={gap:.4f} > {p['reentry_ma_gap']:g}（绝对价格差）"
                    )
                else:
                    reason = f"{mode}退出：{exit_kind}；DIF斜率={row.plot_dif_slope:.4f}，保护线={stop:.2f}"
                if mode == "A零轴反转":
                    window_active = bool(p["enable_a_reentry"] and above_zero)
                # 每次卖出重新要求回落。卖出日已有负斜率可作为这次回落起点。
                pullback_seen = bool(
                    window_active and row.plot_dif_slope <= -p["reentry_pullback"]
                )
        else:
            if window_active and row.plot_dif_slope <= -p["reentry_pullback"]:
                pullback_seen = True
            if i - last_exit <= p["cooldown_bars"]:
                reason = "卖出信号后冷却，避免同一拐点反复交易"
            else:
                if row.candidate_a:
                    entry_kind = "A零轴反转"
                elif window_active and pullback_seen and row.candidate_reentry:
                    entry_kind = "A同波段再入场"
                if entry_kind:
                    action, target, mode = "BUY", 1, entry_kind
                    entry_close, entry_atr, peak_close = row.close, row.atr, row.close
                    stop = (
                        float("nan")
                        if p["enable_a_reentry"] in (2, 3) and mode == "A同波段再入场"
                        else entry_close - p["hard_stop_atr"] * entry_atr
                    )
                    line = stop
                    if mode == "A零轴反转":
                        origin_a_date, reentry_index = row.date, 0
                        # 新 A 尚未卖出，不满足再入场前置条件。
                        window_active = False
                    else:
                        reentry_index += 1
                    if p["enable_a_reentry"] == 3:
                        four_state = {
                            "speed_at": i if row.four_raw_speed else -1000,
                            "effort_at": i if row.four_raw_effort else -1000,
                            "momentum_count": 0, "combo_count": 0,
                        }
                    pullback_seen = False
                    reason = f"{mode}：DIF斜率={row.plot_dif_slope:.4f}，加速度={row.plot_acceleration:.4f}，DEA斜率={row.plot_dea_slope:.4f}"
                    if mode == "A同波段再入场":
                        reason += f"；源A买入={origin_a_date}，本轮第{reentry_index}次再入场；双线未跌破零轴，回落后转强"
                elif window_active:
                    reason = "A交易后的水上观察区间：" + (
                        "已回落，等待DIF转强阈值"
                        if pullback_seen
                        else "等待卖出后的新一轮DIF回落"
                    )
        if window_note:
            reason += "；" + window_note
        rows.append(
            {
                "date": row.date,
                "signal": action,
                "position_target": target,
                "reason": reason,
                "entry_kind": entry_kind,
                "exit_kind": exit_kind,
                "plot_stop": line,
                "reentry_eligible": int(window_active),
                "reentry_pullback_seen": int(pullback_seen),
                "origin_a_date": origin_a_date,
                "reentry_index": reentry_index,
                **(four_flags if p["enable_a_reentry"] == 3 else {}),
            }
        )
    result = pd.DataFrame(
        rows,
        columns=[
            "date",
            "signal",
            "position_target",
            "reason",
            "entry_kind",
            "exit_kind",
            "plot_stop",
            "reentry_eligible",
            "reentry_pullback_seen",
            "origin_a_date",
            "reentry_index",
        ] + (["four_speed", "four_momentum", "four_effort", "four_liquidity"]
             if p["enable_a_reentry"] == 3 else []),
    )
    for column in [
        "macd_dif",
        "macd_dea",
        "macd_hist",
        "plot_dif_slope",
        "plot_dea_slope",
        "plot_acceleration",
        "candidate_a",
        "candidate_reentry",
        "ma5",
        "ma20",
    ]:
        result[column] = d[column]
    result["plot_stop"] = result.plot_stop.astype(float)
    result.attrs["plots"] = [
        {
            "column": "plot_stop",
            "label": "ATR保护线",
            "pane": "price",
            "color": "#b65d5a",
        },
        {"column": "macd_dif", "label": "DIF", "pane": "MACD", "color": "#4b718d"},
        {"column": "macd_dea", "label": "DEA", "pane": "MACD", "color": "#cda519"},
        {
            "column": "plot_dif_slope",
            "label": "DIF斜率 / ATR",
            "pane": "斜率",
            "color": "#087f8c",
        },
        {
            "column": "plot_dea_slope",
            "label": "DEA斜率 / ATR",
            "pane": "斜率",
            "color": "#cda519",
        },
        {
            "column": "plot_acceleration",
            "label": "DIF加速度 / ATR",
            "pane": "斜率",
            "color": "#7761a8",
        },
    ]
    if p["enable_a_reentry"] == 3:
        for column in d.columns:
            if column.startswith("four_"):
                result[column] = d[column]
        result["plot_four_score"] = result[["four_speed", "four_momentum", "four_effort", "four_liquidity"]].sum(axis=1)
        result.attrs["plots"].append({"column": "plot_four_score", "label": "四逻辑预警项数（非概率）", "pane": "四逻辑", "color": "#b65d5a"})
    return result
