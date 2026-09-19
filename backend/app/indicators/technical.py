from collections.abc import Callable
from typing import ClassVar

import numpy as np
import pandas as pd


def _period(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("指标周期必须为正整数")
    return value


def slope(series: pd.Series, period: int = 1) -> pd.Series:
    return series.diff(_period(period)) / period


def sma(series: pd.Series, period: int = 20) -> pd.Series:
    return series.rolling(_period(period), min_periods=period).mean()


def ema(series: pd.Series, period: int = 12) -> pd.Series:
    return series.ewm(span=_period(period), adjust=False, min_periods=period).mean()


def calculate_macd(data: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    if _period(fast) >= _period(slow):
        raise ValueError("MACD fast 必须小于 slow")
    out = data.copy()
    out["macd_dif"] = ema(out.close, fast) - ema(out.close, slow)
    out["macd_dea"] = ema(out.macd_dif, signal)
    out["macd_hist"] = 2 * (out.macd_dif - out.macd_dea)
    return out


def calculate_rsi(data: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    _period(period)
    delta = data.close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rsi = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    rsi = rsi.mask((loss == 0) & (gain > 0), 100).mask((loss == 0) & (gain == 0), 50)
    return data.assign(rsi=rsi)


def calculate_boll(data: pd.DataFrame, period: int = 20, deviations: float = 2) -> pd.DataFrame:
    mid = sma(data.close, period)
    std = data.close.rolling(period).std(ddof=0)
    return data.assign(boll_mid=mid, boll_upper=mid + deviations * std, boll_lower=mid - deviations * std)


def calculate_atr(data: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    _period(period)
    previous = data.close.shift(1)
    tr = pd.concat(
        [data.high - data.low, (data.high - previous).abs(), (data.low - previous).abs()], axis=1
    ).max(axis=1)
    return data.assign(atr=tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean())


def calculate_kdj(data: pd.DataFrame, period: int = 9) -> pd.DataFrame:
    _period(period)
    low = data.low.rolling(period).min()
    high = data.high.rolling(period).max()
    rsv = ((data.close - low) / (high - low).replace(0, np.nan) * 100).mask(high == low, 50)
    k = rsv.ewm(alpha=1 / 3, adjust=False).mean()
    d = k.ewm(alpha=1 / 3, adjust=False).mean()
    return data.assign(kdj_k=k, kdj_d=d, kdj_j=3 * k - 2 * d)


class IndicatorRegistry:
    _items: ClassVar[dict[str, Callable]] = {}

    @classmethod
    def register(cls, name: str, function: Callable):
        cls._items[name] = function

    @classmethod
    def calculate(cls, name: str, data: pd.DataFrame, **params) -> pd.DataFrame:
        if name not in cls._items:
            raise ValueError(f"未知指标：{name}")
        return cls._items[name](data, **params)

    @classmethod
    def names(cls) -> list[str]:
        return list(cls._items)


IndicatorRegistry.register(
    "SMA", lambda data, period=20: data.assign(**{f"sma_{period}": sma(data.close, period)})
)
IndicatorRegistry.register(
    "EMA", lambda data, period=12: data.assign(**{f"ema_{period}": ema(data.close, period)})
)
IndicatorRegistry.register("MACD", calculate_macd)
IndicatorRegistry.register("RSI", calculate_rsi)
IndicatorRegistry.register("BOLL", calculate_boll)
IndicatorRegistry.register("ATR", calculate_atr)
IndicatorRegistry.register("KDJ", calculate_kdj)
IndicatorRegistry.register(
    "VOLUME_MA", lambda data, period=5: data.assign(volume_ma=sma(data.volume, period))
)


def chart_indicators(data: pd.DataFrame) -> pd.DataFrame:
    out = calculate_macd(data)
    out["sma_5"], out["sma_20"] = sma(data.close, 5), sma(data.close, 20)
    for name in ["RSI", "BOLL", "ATR", "KDJ", "VOLUME_MA"]:
        out = IndicatorRegistry.calculate(name, out)
    out["dif_slope"] = slope(out.macd_dif)
    out["dea_slope"] = slope(out.macd_dea)
    return out
