"""New exits must preserve original entries and remain causal."""

import runpy
from pathlib import Path

import pandas as pd
import pytest

from app.strategies.contracts import validate_signals

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def strategy():
    return runpy.run_path(str(ROOT / "examples/000938_exit_research/strategy.py"))


def bars(prices):
    return pd.DataFrame(
        {
            "date": pd.bdate_range("2024-01-01", periods=len(prices)).date,
            "open": prices,
            "close": prices,
            "high": [p + 0.2 for p in prices],
            "low": [p - 0.2 for p in prices],
            "volume": 10000,
        }
    )


def wave():
    return bars(
        [100.0] * 30
        + [100.6 + i * 0.2 for i in range(20)]
        + [
            103.6,
            103.8,
            104,
            104.2,
            104.4,
            104.6,
            104.8,
            99,
            98,
            98,
            99,
            100,
            101,
            102,
            103,
            104,
            105,
            106,
            107,
            100,
            99,
        ]
    )


def test_same_entries_even_after_early_exit(strategy):
    data = wave()
    params = {"max_entry_atr": 10}
    baseline = strategy["_baseline_signals"](data, params)
    actual = validate_signals(strategy["generate_signals"](data, params), data)
    assert baseline.signal.eq("BUY").sum() >= 2
    pd.testing.assert_frame_equal(
        actual[actual.signal.eq("BUY")].reset_index(drop=True),
        baseline[baseline.signal.eq("BUY")].reset_index(drop=True),
    )
    assert ((actual.signal == "SELL") & (baseline.signal == "HOLD")).any()
    wait = actual.reason.str.contains("已提前保护退出")
    assert wait.any()
    assert actual.loc[wait, "position_target"].eq(0).all()
    # Alternative exits never leave the new strategy exposed after the original goes flat.
    assert (actual.position_target <= baseline.position_target).all()


def test_no_protection_activation_matches_original_actions(strategy):
    data = wave()
    expected = strategy["_baseline_signals"](data, {})
    actual = strategy["generate_signals"](data, {"profit_arm_atr": 100000})
    pd.testing.assert_frame_equal(
        actual[["date", "signal", "position_target"]], expected[["date", "signal", "position_target"]]
    )


def test_every_prefix_and_no_input_mutation(strategy):
    data = wave()
    copy = data.copy(deep=True)
    full = strategy["generate_signals"](data, {})
    for stop in range(1, len(data) + 1):
        pd.testing.assert_frame_equal(full.iloc[:stop], strategy["generate_signals"](data.iloc[:stop], {}))
    pd.testing.assert_frame_equal(copy, data)


def test_protection_line_cannot_fall_when_atr_spikes(strategy):
    data = bars([100.0] * 30 + [101, 102, 103, 102, 101])
    data.loc[33, ["high", "low"]] = [120, 90]
    data.loc[34, ["high", "low"]] = [119, 90]
    params = {"atr_period": 1, "profit_arm_atr": 1, "exit_confirm": 50}
    baseline = strategy["_baseline_signals"](data, {"atr_period": 1, "exit_confirm": 50})
    actual = strategy["generate_signals"](data, params)
    assert baseline.iloc[-1].signal == "HOLD"
    assert actual.iloc[-1].signal == "SELL"
    assert "上涨后收紧保护" in actual.iloc[-1].reason
    assert "101.20" in actual.iloc[-1].reason


@pytest.mark.parametrize(
    "params",
    [
        {"profit_arm_atr": 0},
        {"profit_arm_atr": float("nan")},
        {"profit_trailing_atr": 4},
        {"profit_trailing_atr": -1},
        {"profit_trailing_atr": "1.5"},
        {"obsolete": 1},
    ],
)
def test_invalid_guard_params(strategy, params):
    with pytest.raises(ValueError):
        strategy["generate_signals"](wave(), params)
