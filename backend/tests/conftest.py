import pandas as pd
import pytest

from app.data.sample import SampleProvider
from app.database.repository import Repository


@pytest.fixture
def repository(tmp_path):
    return Repository(tmp_path / "test.duckdb")


@pytest.fixture
def sample_bars():
    from datetime import date

    return SampleProvider().get_daily_bars("000938", date(2023, 1, 1), date(2025, 1, 1), "raw")


def make_bars(prices):
    return pd.DataFrame(
        {
            "date": pd.bdate_range("2024-01-01", periods=len(prices)).date,
            "open": prices,
            "high": prices,
            "low": prices,
            "close": prices,
            "volume": 10000,
        }
    )


def make_signals(bars, actions):
    target, rows = 0, []
    for day, action in zip(bars.date, actions):
        if action == "BUY":
            target = 1
        elif action == "SELL":
            target = 0
        rows.append({"date": day, "signal": action, "position_target": target, "reason": f"test {action}"})
    return pd.DataFrame(rows)
