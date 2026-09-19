from datetime import date
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import settings

Adjust = Literal["raw", "qfq", "hfq"]
Source = Literal["eastmoney", "tencent", "sample"]
Symbol = Annotated[str, Field(pattern=r"^\d{6}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class DataRequest(StrictModel):
    symbol: Symbol
    start_date: date
    end_date: date
    adjust: Adjust = "qfq"
    source: Source = "eastmoney"
    force_refresh: bool = False

    @model_validator(mode="after")
    def dates_ordered(self):
        if self.start_date > self.end_date:
            raise ValueError("开始日期不能晚于结束日期")
        if (self.end_date - self.start_date).days > 365 * 40:
            raise ValueError("一次最多查询 40 年数据")
        return self


class BacktestConfig(StrictModel):
    initial_cash: float = Field(default=100000, gt=0, le=1e12)
    commission_rate: float = Field(default=settings.default_commission, ge=0, le=0.1)
    minimum_commission: float = Field(default=5, ge=0, le=10000)
    stamp_tax_rate: float = Field(default=0.0005, ge=0, le=0.1)
    slippage: float = Field(default=0.001, ge=0, lt=0.1)
    signal_timing: Literal["signal_at_close"] = "signal_at_close"
    execution_timing: Literal["execute_next_open"] = "execute_next_open"


class BacktestRequest(DataRequest):
    strategy_name: str = "ma_cross"
    parameters: dict[str, int | float] = Field(default_factory=dict)
    config: BacktestConfig = Field(default_factory=BacktestConfig)
