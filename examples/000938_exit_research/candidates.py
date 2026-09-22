"""从已保存的买入策略构造少量退出候选，精确替换并检查，避免悄悄改动入口。"""

from pathlib import Path

BASE_PATH = Path(__file__).resolve().parents[1] / "000938_swing" / "strategy.py"
NAMES = {
    "baseline": "原版EMA20/3ATR",
    "ema10": "EMA10两日退出",
    "profit_guard": "上涨2ATR后收紧至1.5ATR",
    "structure": "跌破此前3日最低价",
}


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError("基准源码发生变化，请先人工核对候选构建逻辑")
    return source.replace(old, new, 1)


def candidate_source(kind):
    if kind == "locked_guard":
        return locked_source()
    source = BASE_PATH.read_text(encoding="utf-8")
    if kind == "baseline":
        return source
    if kind == "ema10":
        source = replace_once(
            source,
            '    "momentum_ema": 5,',
            '    "exit_ema": 10,  # 独立退出均线，不改变入场EMA\n    "momentum_ema": 5,',
        )
        source = replace_once(
            source,
            '        "momentum_ema",',
            '        "exit_ema",\n        "momentum_ema",',
        )
        source = replace_once(
            source,
            "    below_trend = (close < trend)",
            '    exit_line = ema(close, p["exit_ema"])\n    below_trend = (close < exit_line)',
        )
        source = replace_once(
            source, "根收盘跌破 EMA{p['trend_ema']}", "根收盘跌破 EMA{p['exit_ema']}"
        )
    elif kind == "profit_guard":
        source = replace_once(
            source,
            '    "momentum_ema": 5,',
            """    "profit_arm_atr": 2.0,  # 相对买入信号收盘上涨2个信号ATR，激活保护
    "profit_trailing_atr": 1.5,  # 激活后跟随距离收紧；不是保证成交的止损价
    "momentum_ema": 5,""",
        )
        source = replace_once(
            source,
            "    d = calculate_atr",
            """    if p["profit_arm_atr"] <= 0 or not 0 < p["profit_trailing_atr"] <= p["trailing_atr"]:
        raise ValueError("保护激活倍数必须为正，保护跟随倍数须大于0且不超过原跟随倍数")

    d = calculate_atr""",
        )
        source = replace_once(
            source,
            "    trailing_line = None\n    for i, day",
            "    trailing_line = None\n    entry_signal_price = entry_signal_atr = None\n    protection_active = False\n    for i, day",
        )
        source = replace_once(
            source,
            """            trailing_line = max(
                trailing_line, peak_close - p["trailing_atr"] * atr.iloc[i]
            )""",
            """            # 只使用信号价格/ATR；策略拿不到实际成交价。
            if peak_close - entry_signal_price >= p["profit_arm_atr"] * entry_signal_atr:
                protection_active = True
            distance = p["profit_trailing_atr"] if protection_active else p["trailing_atr"]
            trailing_line = max(trailing_line, peak_close - distance * atr.iloc[i])""",
        )
        source = replace_once(
            source,
            '                exits.append(f"收盘跌至信号 ATR 跟随线 {trailing_line:.2f} 以下")',
            """                stage = "上涨后收紧保护" if protection_active else "初始波动保护"
                exits.append(f"{stage}：收盘跌至信号 ATR 跟随线 {trailing_line:.2f} 以下")""",
        )
        source = replace_once(
            source,
            "            peak_close = price\n            trailing_line =",
            "            peak_close = price\n            entry_signal_price, entry_signal_atr = price, atr.iloc[i]\n            protection_active = False\n            trailing_line =",
        )
    elif kind == "structure":
        source = replace_once(
            source,
            '    "momentum_ema": 5,',
            '    "structure_period": 3,  # 结构低点不含当天\n    "momentum_ema": 5,',
        )
        source = replace_once(
            source,
            '        "momentum_ema",',
            '        "structure_period",\n        "momentum_ema",',
        )
        source = replace_once(
            source,
            "    below_trend =",
            '    structure_low = d["low"].rolling(p["structure_period"]).min().shift(1)\n    below_trend =',
        )
        source = replace_once(
            source,
            "            exits = []",
            """            exits = []
            if price < structure_low.iloc[i]:
                exits.append(f"收盘跌破此前 {p['structure_period']} 根最低价 {structure_low.iloc[i]:.2f}")""",
        )
    else:
        raise ValueError(kind)
    return source


def load_candidate(kind, fixed_entry=False):
    if kind == "locked_guard" and fixed_entry:
        return load_candidate("profit_guard", fixed_entry=True)
    source = candidate_source(kind)
    if fixed_entry:
        source = replace_once(
            source,
            "def generate_signals(data, params):",
            "def generate_signals(data, params, forced_entry_index=None):",
        )
        source = replace_once(
            source,
            "        elif buy.iloc[i]:",
            "        elif (buy.iloc[i] if forced_entry_index is None else i == forced_entry_index):",
        )
    namespace = {}
    exec(compile(source, f"candidate_{kind}.py", "exec"), namespace)  # noqa: S102 -- trusted local research source
    return namespace["generate_signals"], namespace["DEFAULT_PARAMS"]


def locked_source():
    base = BASE_PATH.read_text(encoding="utf-8")
    base = base.replace("DEFAULT_PARAMS", "BASE_PARAMS")
    base = base.replace(
        "000938 波段启动观察 V2：短期动量转强 + 小平台突破。",
        "000938 波段启动：原买点 + 上涨后分段保护退出。",
    )
    base = replace_once(
        base,
        "def generate_signals(data, params):",
        "def _baseline_signals(data, params):",
    )
    return (
        base
        + '''

# 保留原买入日：基准信号仅依赖当日和历史，提前退出后不新增重入信号。
DEFAULT_PARAMS = {
    **BASE_PARAMS,
    "profit_arm_atr": 2.0,  # 买入信号价至最高收盘上涨2个信号ATR后激活
    "profit_trailing_atr": 1.5,  # 激活后跟随距离；不可保证按线价成交
}


def generate_signals(data, params):
    """分段保护卖出，保持基准BUY信号的日期和原因。"""
    unknown = set(params) - set(DEFAULT_PARAMS)
    if unknown:
        raise ValueError(f"请删除旧策略参数：{', '.join(sorted(unknown))}")
    p = {**DEFAULT_PARAMS, **params}
    for key in ["profit_arm_atr", "profit_trailing_atr"]:
        if not isinstance(p[key], (int, float)) or not math.isfinite(p[key]) or p[key] <= 0:
            raise ValueError(f"{key} 必须是有限正数")
    if p["profit_trailing_atr"] > p["trailing_atr"]:
        raise ValueError("保护距离不能超过原始跟随距离")
    baseline = _baseline_signals(data, {k: p[k] for k in BASE_PARAMS})
    d = calculate_atr(data.copy().reset_index(drop=True), p["atr_period"])
    rows, target = [], 0
    entry_price = entry_atr = peak_close = protection_line = None
    armed = False
    for i, day in enumerate(d["date"]):
        price, atr = d["close"].iloc[i], d["atr"].iloc[i]
        original = baseline.iloc[i]
        action, reason = ("HOLD", "保持目标持仓，等待退出") if target else ("NONE", "等待原策略下个买入点")
        if target:
            peak_close = max(peak_close, price)
            if peak_close - entry_price >= p["profit_arm_atr"] * entry_atr:
                armed = True
            distance = p["profit_trailing_atr"] if armed else p["trailing_atr"]
            protection_line = max(protection_line, peak_close - distance * atr)
            exits = []
            if original.signal == "SELL":
                exits.append(original.reason)
            if armed and price <= protection_line:
                exits.append(f"上涨后收紧保护：收盘跌至信号ATR跟随线 {protection_line:.2f} 以下")
            if exits:
                action, target, reason = "SELL", 0, "；".join(exits)
                entry_price = entry_atr = peak_close = protection_line = None
                armed = False
        elif original.signal == "BUY":
            action, target, reason = "BUY", 1, original.reason
            entry_price, entry_atr, peak_close = price, atr, price
            protection_line = price - p["trailing_atr"] * atr
            armed = False
        elif original.position_target == 1:
            reason = "已提前保护退出，等待原策略本轮结束，不新增追入"
        rows.append({"date": day, "signal": action, "position_target": target, "reason": reason})
    return pd.DataFrame(rows, columns=["date", "signal", "position_target", "reason"])
'''
    )


NAMES["locked_guard"] = "收紧保护且保留原买点"
