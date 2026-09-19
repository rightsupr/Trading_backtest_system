import pytest
from conftest import make_bars, make_signals

from app.backtest.engine import BacktestEngine
from app.models.schemas import BacktestConfig


def run(prices, actions, **config):
    bars = make_bars(prices)
    return BacktestEngine().run("000938", bars, make_signals(bars, actions), BacktestConfig(**config))


def test_next_open_fees_and_trade_accounting():
    result = run(
        [9.0, 10.0, 12.0, 11.0],
        ["BUY", "HOLD", "SELL", "NONE"],
        initial_cash=10005,
        commission_rate=0,
        minimum_commission=5,
        slippage=0,
        stamp_tax_rate=0.001,
    )
    trade = result["trades"][0]
    assert trade["entry_date"].isoformat() == "2024-01-02"
    assert trade["entry_price"] == 10
    assert trade["exit_price"] == 11
    assert trade["shares"] == 1000
    assert trade["commission"] == 10
    assert trade["tax"] == 11
    assert trade["profit"] == 979
    assert trade["net_return"] == pytest.approx(979 / 10005)
    assert trade["gross_return"] == pytest.approx(0.1)
    assert trade["MFE"] == pytest.approx(0.2)
    assert trade["MAE"] == 0
    assert result["metrics"]["final_equity"] == 10984
    assert result["metrics"]["max_drawdown"] == pytest.approx(10984 / 12000 - 1)


def test_slippage_lots_and_minimum_commission():
    result = run([10.0, 10.0, 10.0], ["BUY", "SELL", "NONE"], initial_cash=10000, slippage=0.01)
    trade = result["trades"][0]
    assert trade["shares"] == 900
    assert trade["entry_price"] == pytest.approx(10.1)
    assert trade["exit_price"] == pytest.approx(9.9)
    assert trade["profit"] < -180
    assert all(e["cash"] >= 0 for e in result["equity"])


def test_no_same_day_fill_and_no_forced_exit():
    result = run([10.0, 12.0], ["NONE", "BUY"])
    assert result["fills"] == []
    result = run([10.0, 12.0, 13.0], ["BUY", "HOLD", "HOLD"], slippage=0)
    assert result["trades"] == []
    assert result["open_position"]["entry_price"] == 12
    assert result["equity"][-1]["position_value"] > 0


def test_insufficient_cash_is_explained():
    result = run([100.0, 100.0], ["BUY", "HOLD"], initial_cash=100)
    assert result["metrics"]["number_of_trades"] == 0
    assert result["rejected_orders"][0]["reason"].startswith("资金不足")


def test_exit_day_high_low_are_not_used():
    bars = make_bars([10.0, 10.0, 11.0])
    bars.loc[2, ["high", "low", "close"]] = [100, 1, 90]
    result = BacktestEngine().run(
        "000938", bars, make_signals(bars, ["BUY", "SELL", "NONE"]), BacktestConfig(slippage=0)
    )
    assert result["trades"][0]["MFE"] == pytest.approx(0.1)
    assert result["trades"][0]["MAE"] == 0


def test_suspension_delays_order():
    bars = make_bars([10.0, 11.0, 12.0, 13.0])
    bars.loc[1, "volume"] = 0
    result = BacktestEngine().run(
        "000938", bars, make_signals(bars, ["BUY", "HOLD", "SELL", "NONE"]), BacktestConfig(slippage=0)
    )
    assert result["trades"][0]["entry_price"] == 12
    assert len(result["rejected_orders"]) == 1
