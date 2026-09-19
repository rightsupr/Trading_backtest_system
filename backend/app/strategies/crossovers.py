import pandas as pd
from pydantic import Field, model_validator

from app.indicators.technical import calculate_macd, sma
from app.models.schemas import StrictModel
from app.strategies.base import BaseStrategy, crossover_signals


class MAParameters(StrictModel):
    fast_ma: int = Field(default=5, ge=1, le=250, strict=True)
    slow_ma: int = Field(default=20, ge=2, le=500, strict=True)

    @model_validator(mode="after")
    def ordered(self):
        if self.fast_ma >= self.slow_ma:
            raise ValueError("fast_ma 必须小于 slow_ma")
        return self


class MACDParameters(StrictModel):
    fast: int = Field(default=12, ge=1, le=250, strict=True)
    slow: int = Field(default=26, ge=2, le=500, strict=True)
    signal: int = Field(default=9, ge=1, le=250, strict=True)

    @model_validator(mode="after")
    def ordered(self):
        if self.fast >= self.slow:
            raise ValueError("fast 必须小于 slow")
        return self


class MovingAverageStrategy(BaseStrategy):
    name, label, parameter_model = "ma_cross", "均线金叉", MAParameters

    def prepare(self, data: pd.DataFrame, params: dict) -> pd.DataFrame:
        return data.assign(
            strategy_fast=sma(data.close, params["fast_ma"]), strategy_slow=sma(data.close, params["slow_ma"])
        )

    def generate_signals(self, data: pd.DataFrame, params: dict) -> pd.DataFrame:
        return crossover_signals(
            data, data.strategy_fast, data.strategy_slow, f"MA{params['fast_ma']} / MA{params['slow_ma']}"
        )


class MACDStrategy(BaseStrategy):
    name, label, parameter_model = "macd", "MACD 基础策略", MACDParameters

    def prepare(self, data: pd.DataFrame, params: dict) -> pd.DataFrame:
        return calculate_macd(data, **params)

    def generate_signals(self, data: pd.DataFrame, params: dict) -> pd.DataFrame:
        return crossover_signals(data, data.macd_dif, data.macd_dea, "DIF / DEA")
