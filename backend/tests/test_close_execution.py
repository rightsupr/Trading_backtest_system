import pytest
from conftest import make_bars, make_signals

from app.backtest.engine import BacktestEngine
from app.models.schemas import BacktestConfig


def execute(bars, actions, **kwargs):
    return BacktestEngine().run("000938", bars, make_signals(bars, actions), BacktestConfig(**kwargs))


def test_default_close_fills_fees_equity_and_final_day_exit():
    bars = make_bars([50.0, 60.0, 70.0])
    bars["close"] = [10.0, 12.0, 11.0]
    bars["high"], bars["low"] = bars.close, bars.close
    result = execute(
        bars,
        ["BUY", "HOLD", "SELL"],
        initial_cash=10005,
        commission_rate=0,
        minimum_commission=5,
        slippage=0,
        stamp_tax_rate=0.001,
    )
    assert BacktestConfig().execution_timing == "execute_same_close"
    trade = result["trades"][0]
    assert trade["entry_date"] == trade["entry_signal_date"] == bars.date[0]
    assert trade["exit_date"] == trade["exit_signal_date"] == bars.date[2]
    assert [f["price"] for f in result["fills"]] == [10, 11]
    assert all(f["date"] == f["signal_date"] for f in result["fills"])
    assert trade["shares"] == 1000
    assert trade["commission"] == 10
    assert trade["tax"] == 11
    assert trade["profit"] == 979
    assert trade["net_return"] == pytest.approx(979 / 10005)
    assert trade["holding_bars"] == trade["holding_days"] == 2
    assert [e["total_equity"] for e in result["equity"]] == [10000, 12000, 10984]
    assert result["metrics"]["max_drawdown"] == pytest.approx(10984 / 12000 - 1)
    assert result["open_position"] is None


def test_entry_intraday_extremes_excluded_exit_session_included():
    bars = make_bars([10.0, 11.0])
    bars["high"], bars["low"] = [100.0, 15.0], [1.0, 8.0]
    result = execute(bars, ["BUY", "SELL"], slippage=0)
    trade = result["trades"][0]
    assert trade["MFE"] == pytest.approx(0.5)
    assert trade["MAE"] == pytest.approx(-0.2)
    assert trade["holding_bars"] == 1  # One signal/action per date preserves T+1.


def test_close_drawdown_includes_exit_day():
    bars = make_bars([10.0, 15.0, 12.0])
    trade = execute(bars, ["BUY", "HOLD", "SELL"], slippage=0)["trades"][0]
    assert trade["max_drawdown_during_trade"] == pytest.approx(-0.2)


def test_last_bar_buy_is_filled_without_forced_exit():
    bars = make_bars([10.0])
    result = execute(bars, ["BUY"], slippage=0)
    assert len(result["fills"]) == 1
    assert result["fills"][0]["date"] == bars.date[0]
    assert result["trades"] == []
    assert result["open_position"]["entry_price"] == 10
    assert result["equity"][0]["position_value"] > 0


def test_slippage_lots_and_fees_still_apply_to_close():
    bars = make_bars([99.0, 99.0])
    bars["close"] = [10.0, 10.0]
    result = execute(bars, ["BUY", "SELL"], initial_cash=10000, slippage=0.01)
    trade = result["trades"][0]
    assert trade["shares"] == 900
    assert trade["entry_price"] == pytest.approx(10.1)
    assert trade["exit_price"] == pytest.approx(9.9)
    assert trade["profit"] < -180
    assert all(e["cash"] >= 0 for e in result["equity"])


def test_suspension_delays_until_tradable_close_and_preserves_signal_date():
    bars = make_bars([10.0, 11.0, 12.0, 13.0])
    bars["volume"] = [0, 10000, 0, 10000]
    result = execute(bars, ["BUY", "HOLD", "SELL", "NONE"], slippage=0)
    assert [f["price"] for f in result["fills"]] == [11, 13]
    assert [f["signal_date"] for f in result["fills"]] == [bars.date[0], bars.date[2]]
    assert len(result["rejected_orders"]) == 2


def test_opposite_signal_cancels_suspended_buy():
    bars = make_bars([10.0, 11.0])
    bars.loc[0, "volume"] = 0
    result = execute(bars, ["BUY", "SELL"])
    assert result["fills"] == []
    assert result["open_position"] is None


def test_close_order_with_insufficient_cash_is_rejected():
    result = execute(make_bars([100.0]), ["BUY"], initial_cash=100)
    assert not result["fills"]
    assert result["rejected_orders"][0]["reason"].startswith("资金不足")
