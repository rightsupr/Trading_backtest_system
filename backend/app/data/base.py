from abc import ABC, abstractmethod
from datetime import date

import numpy as np
import pandas as pd


class ProviderError(Exception):
    pass


class AdjustmentChanged(ProviderError):
    pass


class BaseMarketDataProvider(ABC):
    name: str

    @abstractmethod
    def get_daily_bars(self, symbol: str, start_date: date, end_date: date, adjust: str) -> pd.DataFrame:
        """Return ascending daily bars; volume in shares, amount in CNY, percentages in percent units."""


def validate_bars(data: pd.DataFrame) -> pd.DataFrame:
    if data.empty:
        return data
    required = ["date", "open", "high", "low", "close", "volume"]
    if not set(required).issubset(data.columns):
        raise ProviderError("数据源缺少必需行情字段")
    data = data.copy()
    data["date"] = pd.to_datetime(data["date"]).dt.date
    for col in required[1:] + ["amount", "turnover", "pre_close", "change", "pct_change"]:
        data[col] = pd.to_numeric(data.get(col, float("nan")), errors="coerce")
    if not np.isfinite(data[required[1:]].to_numpy()).all():
        raise ProviderError("行情包含空值或非有限价格")
    invalid = (
        (data[["open", "high", "low", "close"]] <= 0).any(axis=1)
        | (data.volume < 0)
        | (data.high < data[["open", "close", "low"]].max(axis=1))
        | (data.low > data[["open", "close", "high"]].min(axis=1))
    )
    if invalid.any():
        raise ProviderError("行情价格或成交量不合法；请检查复权方式或数据源")
    return data.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)
