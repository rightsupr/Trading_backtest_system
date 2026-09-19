from abc import ABC, abstractmethod

import pandas as pd
from pydantic import BaseModel


class BaseStrategy(ABC):
    name: str
    label: str
    version = "1.0.0"
    parameter_model: type[BaseModel]

    def validate_params(self, params: dict) -> dict:
        return self.parameter_model.model_validate(params).model_dump()

    @abstractmethod
    def prepare(self, data: pd.DataFrame, params: dict) -> pd.DataFrame:
        """Declare indicator calculation separately from the signal rules."""

    @abstractmethod
    def generate_signals(self, data: pd.DataFrame, params: dict) -> pd.DataFrame:
        """Each row may use only that row and preceding rows. No database access."""


def crossover_signals(data: pd.DataFrame, fast: pd.Series, slow: pd.Series, label: str) -> pd.DataFrame:
    upward = (fast > slow) & (fast.shift(1) <= slow.shift(1))
    downward = (fast < slow) & (fast.shift(1) >= slow.shift(1))
    target = 0
    rows = []
    for i, day in enumerate(data.date):
        signal, reason = ("HOLD", "保持目标持仓") if target else ("NONE", "等待入场信号")
        if upward.iloc[i]:
            target, signal, reason = 1, "BUY", f"{label} 上穿，收盘确认"
        elif downward.iloc[i]:
            target, signal, reason = 0, "SELL", f"{label} 下穿，收盘确认"
        rows.append({"date": day, "signal": signal, "position_target": target, "reason": reason})
    return pd.DataFrame(rows)
