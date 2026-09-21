"""Behavioral checks for the editable swing example, using synthetic prices only."""

import runpy
from pathlib import Path

import pandas as pd
import pytest

from app.strategies.contracts import validate_signals


@pytest.fixture(scope="module")
def generate():
    path = Path(__file__).resolve().parents[2] / "examples/000938_swing/strategy.py"
    return runpy.run_path(str(path))["generate_signals"]


def bars(prices):
    return pd.DataFrame(
        {
            "date": pd.bdate_range("2024-01-01", periods=len(prices)).date,
            "open": prices,
            "high": [price + 0.1 for price in prices],
            "low": [price - 0.1 for price in prices],
            "close": prices,
            "volume": 10000,
        }
    )


def test_default_contract_warmup_and_no_fixed_holding_limit(generate):
    data = bars([100.0] * 30 + [100.4 + i * 0.2 for i in range(80)])
    original = data.copy(deep=True)
    params = {}
    result = validate_signals(generate(data, params), data)

    # A complete quiet warmup is followed by one breakout and a sustained trend.
    assert result.iloc[:30].signal.eq("NONE").all()
    assert result.iloc[30].signal == "BUY"
    assert result.iloc[31:].signal.eq("HOLD").all()
    assert result.iloc[-1].position_target == 1
    assert len(result.iloc[31:]) > 30
    pd.testing.assert_frame_equal(data, original)
    assert params == {}


def test_rising_prices_cannot_buy_before_default_indicator_warmup(generate):
    # Wide lower ranges make the extension filter permissive, isolating warmup.
    data = bars([100 + i * 0.1 for i in range(28)])
    data["high"] = data.close + 0.01
    data["low"] = data.close - 2
    result = generate(data, {})
    assert result.iloc[:22].signal.eq("NONE").all()
    assert result.iloc[22].signal == "BUY"


def test_future_prices_never_rewrite_previous_signals_or_reasons(generate):
    data = bars(
        [100.0] * 30
        + [100.4 + i * 0.2 for i in range(40)]
        + [107, 104, 100, 95, 93, 96, 100, 103, 106, 108, 110]
    )
    full = validate_signals(generate(data, {}), data)
    assert full.signal.eq("BUY").any()
    assert full.signal.eq("SELL").any()
    # Check every nonempty historical prefix, including entry and exit boundaries.
    for stop in range(1, len(data) + 1):
        prefix = generate(data.iloc[:stop], {})
        pd.testing.assert_frame_equal(full.iloc[:stop], prefix)


def test_breakout_uses_previous_highs_but_not_todays_high(generate):
    data = bars([100.0] * 30 + [100.8])
    data.loc[30, "high"] = 110.0
    assert data.iloc[-1].close < data.iloc[-1].high
    assert generate(data, {}).iloc[-1].signal == "BUY"

    # An actual prior high above the same close must block the entry.
    data.loc[29, "high"] = 101.0
    assert generate(data, {}).iloc[-1].signal == "NONE"


def test_exit_cooldown_blocks_an_otherwise_valid_reentry(generate):
    data = bars([100.0] * 30 + [100.5, 100.8, 99, 98, 101, 102, 103, 104])
    params = {
        "momentum_ema": 2,
        "trend_ema": 3,
        "trend_slope": 1,
        "breakout_period": 1,
        "atr_period": 2,
        "max_entry_atr": 10,
        "trailing_atr": 100,  # Isolate the trend exit from the trailing exit.
        "exit_confirm": 1,
        "cooldown_bars": 3,
    }
    result = validate_signals(generate(data, params), data)
    assert result.iloc[30:37].signal.tolist() == [
        "BUY", "HOLD", "SELL", "NONE", "NONE", "NONE", "BUY"
    ]
    assert result.iloc[33:36].reason.str.contains("冷却期").all()
    without_cooldown = generate(data, {**params, "cooldown_bars": 0})
    assert without_cooldown.iloc[34].signal == "BUY"


def test_recovery_resets_the_consecutive_closes_exit(generate):
    data = bars([100.0] * 30 + [100.4, 101, 99.9, 101, 99.9, 99.8])
    result = generate(data, {"trailing_atr": 100})
    # Two isolated dips are insufficient: the recovery between them resets the
    # confirmation, and only the final consecutive pair causes the default exit.
    assert result.iloc[30:].signal.tolist() == ["BUY", "HOLD", "HOLD", "HOLD", "HOLD", "SELL"]
    assert "连续 2 根" in result.iloc[-1].reason


def test_volatility_spike_cannot_lower_an_existing_trailing_line(generate):
    data = bars([100.0] * 30 + [101, 102, 103, 102, 100.5])
    # Large daily ranges inflate ATR after a profitable move. The old follow-up
    # line must survive the inflation and exit when the close crosses below it.
    data.loc[33, ["high", "low"]] = [120.0, 90.0]
    data.loc[34, ["high", "low"]] = [119.0, 90.0]
    params = {"atr_period": 1, "trailing_atr": 2, "exit_confirm": 50}
    result = validate_signals(generate(data, params), data)
    assert result.iloc[30:].signal.tolist() == ["BUY", "HOLD", "HOLD", "HOLD", "SELL"]
    assert "ATR 跟随线 100.80" in result.iloc[-1].reason
    assert "连续" not in result.iloc[-1].reason


@pytest.mark.parametrize(
    "params, message",
    [
        ({"slope_period": 1}, "旧策略参数"),
        ({"momentum_ema": 20}, "momentum_ema 必须小于"),
        ({"trend_ema": 0}, "整数"),
        ({"breakout_period": 1.5}, "整数"),
        ({"cooldown_bars": -1}, "整数"),
        ({"atr_period": "14"}, "有限数值"),
        ({"max_entry_atr": float("nan")}, "有限数值"),
        ({"trailing_atr": float("inf")}, "有限数值"),
        ({"trailing_atr": 0}, "ATR 倍数必须为正"),
        ({"max_entry_atr": -1}, "ATR 倍数必须为正"),
    ],
)
def test_invalid_parameters_fail_before_producing_signals(generate, params, message):
    with pytest.raises(ValueError, match=message):
        generate(bars([100.0] * 30), params)
