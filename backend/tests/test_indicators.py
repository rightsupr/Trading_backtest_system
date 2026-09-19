import numpy as np
import pandas as pd
import pytest

from app.indicators.technical import IndicatorRegistry, calculate_macd, chart_indicators, slope, sma
from app.strategies import STRATEGIES


def test_ma_and_slope():
    series = pd.Series([1.0, 2.0, 3.0, 7.0])
    assert sma(series, 3).iloc[2] == 2
    assert sma(series, 3).iloc[:2].isna().all()
    assert slope(series, 2).iloc[-1] == 2.5
    with pytest.raises(ValueError):
        slope(series, 0)


def test_macd_reference():
    frame = pd.DataFrame({"close": np.arange(1.0, 61.0)})
    result = calculate_macd(frame, 3, 5, 2)
    fast, slow, dea = 1.0, 1.0, None
    for i, value in enumerate(frame.close):
        fast = 0.5 * value + 0.5 * fast
        slow = (1 / 3) * value + (2 / 3) * slow
        if i >= 4:
            dif = fast - slow
            dea = dif if dea is None else (2 / 3) * dif + (1 / 3) * dea
    assert result.iloc[-1].macd_dif == pytest.approx(dif)
    assert result.iloc[-1].macd_dea == pytest.approx(dea)
    assert result.iloc[-1].macd_hist == pytest.approx(2 * (dif - dea))
    assert "macd_dif" not in frame


def test_all_indicators_and_strategies_are_prefix_invariant(sample_bars):
    full = chart_indicators(sample_bars)
    prefix = chart_indicators(sample_bars.iloc[:110])
    pd.testing.assert_frame_equal(full.iloc[:110], prefix)
    assert len(IndicatorRegistry.names()) == 8
    for strategy in STRATEGIES.values():
        params = strategy.validate_params({})
        signals = strategy.generate_signals(strategy.prepare(full, params), params)
        partial = strategy.generate_signals(strategy.prepare(prefix, params), params)
        pd.testing.assert_frame_equal(signals.iloc[:110], partial)


def test_parameter_rejection():
    with pytest.raises(ValueError):
        STRATEGIES["ma_cross"].validate_params({"fast_ma": 20, "slow_ma": 5})
