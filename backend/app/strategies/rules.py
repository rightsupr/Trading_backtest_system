"""Causal rule evaluation. Rules request indicator functions, never implement their math."""

import pandas as pd

from app.indicators.technical import IndicatorRegistry, slope
from app.models.strategy import Operand, RuleDefinition, RuleGroup

LABELS = {"sma": "SMA", "ema": "EMA", "volume_ma": "成交量均线", "constant": "常数"}
OPERATORS = {"gt": ">", "gte": "≥", "lt": "<", "lte": "≤", "cross_up": "上穿", "cross_down": "下穿"}


def operand_label(value: Operand) -> str:
    if value.feature == "constant":
        return str(value.value)
    name = LABELS.get(value.feature, value.feature)
    if value.feature in ("sma", "ema", "volume_ma"):
        name += f"({value.period})"
    if value.slope_period:
        name += f"斜率({value.slope_period})"
    if value.offset:
        name += f"[{value.offset}根前]"
    return name


def operand_series(data: pd.DataFrame, operand: Operand) -> pd.Series:
    feature = operand.feature
    if feature == "constant":
        values = pd.Series(operand.value, index=data.index)
    elif feature in ("sma", "ema", "volume_ma"):
        indicator = {"sma": "SMA", "ema": "EMA", "volume_ma": "VOLUME_MA"}[feature]
        field = feature if feature == "volume_ma" else f"{feature}_{operand.period}"
        values = IndicatorRegistry.calculate(indicator, data, period=operand.period)[field]
    else:
        values = data[feature]
    if operand.slope_period:
        values = slope(values, operand.slope_period)
    return values.shift(operand.offset)


def evaluate_group(data: pd.DataFrame, group: RuleGroup) -> tuple[pd.Series, list]:
    masks, details = [], []
    for condition in group.conditions:
        left, right = operand_series(data, condition.left), operand_series(data, condition.right)
        op = condition.operator
        if op == "cross_up":
            mask = (left > right) & (left.shift(1) <= right.shift(1))
        elif op == "cross_down":
            mask = (left < right) & (left.shift(1) >= right.shift(1))
        else:
            mask = {"gt": left.gt, "gte": left.ge, "lt": left.lt, "lte": left.le}[op](right)
        mask = mask & left.notna() & right.notna()
        mask = (
            mask.rolling(condition.consecutive, min_periods=condition.consecutive)
            .sum()
            .eq(condition.consecutive)
        )
        label = f"{operand_label(condition.left)} {OPERATORS[op]} {operand_label(condition.right)}"
        if condition.consecutive > 1:
            label += f" 连续{condition.consecutive}根"
        masks.append(mask)
        details.append((mask, label, left, right))
    conditions = pd.concat(masks, axis=1)
    return (conditions.all(axis=1) if group.match == "all" else conditions.any(axis=1)), details


def generate_rule_signals(data: pd.DataFrame, rules: RuleDefinition) -> pd.DataFrame:
    buy, buy_details = evaluate_group(data, rules.buy)
    sell, sell_details = evaluate_group(data, rules.sell)
    rows, target = [], 0
    for i, day in enumerate(data.date):
        action, reason = ("HOLD", "保持目标持仓") if target else ("NONE", "等待买入条件")
        triggered = []
        # Exit has priority even when both groups match on an empty position.
        if bool(sell.iloc[i]):
            if target:
                action, target, triggered = "SELL", 0, sell_details
            else:
                reason = "卖出条件成立，保持空仓（卖出优先）"
        elif bool(buy.iloc[i]) and not target:
            action, target, triggered = "BUY", 1, buy_details
        if triggered:
            reason = "；".join(
                f"{label}（当前 {left.iloc[i]:.5g} / {right.iloc[i]:.5g}）"
                for mask, label, left, right in triggered
                if mask.iloc[i]
            )
        rows.append({"date": day, "signal": action, "position_target": target, "reason": reason})
    return pd.DataFrame(rows)
