from datetime import date

import numpy as np
import pandas as pd

from app.data.base import BaseMarketDataProvider, validate_bars


class SampleProvider(BaseMarketDataProvider):
    """Deterministic synthetic fixture, explicitly isolated from real market data."""

    name = "sample"

    def get_daily_bars(self, symbol: str, start_date: date, end_date: date, adjust: str) -> pd.DataFrame:
        dates = pd.bdate_range("1990-01-01", max(end_date, date(1990, 1, 1)))
        t = np.arange(len(dates))
        rng = np.random.default_rng(int(symbol))
        close = 22 * np.exp(0.000045 * t + 0.13 * np.sin(t / 19) + 0.06 * np.sin(t / 7))
        close *= np.exp(rng.normal(0, 0.008, len(t)))
        previous = np.r_[close[0], close[:-1]]
        opening_rng = np.random.default_rng(int(symbol) + 1)
        opening = previous * (1 + opening_rng.normal(0, 0.006, len(t)))
        volume = (5000000 + 2000000 * np.sin(t / 9) ** 2).astype(int)
        frame = pd.DataFrame(
            {
                "date": dates.date,
                "open": opening,
                "close": close,
                "high": np.maximum(opening, close) * 1.012,
                "low": np.minimum(opening, close) * 0.988,
                "volume": volume,
                "amount": volume * close,
                "turnover": volume / 1e7,
                "pre_close": previous,
                "change": close - previous,
                "pct_change": (close / previous - 1) * 100,
            }
        )
        return validate_bars(frame[(frame.date >= start_date) & (frame.date <= end_date)])
