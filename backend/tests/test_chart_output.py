import copy

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.strategies.chart_output import chart_output
from app.strategies.python_runner import run_python_strategy
from app.strategies.templates import PYTHON_EXAMPLES


def test_python_plot_values_match_strategy_and_warmup(sample_bars):
    template = PYTHON_EXAMPLES[0]
    signals = run_python_strategy(sample_bars, template["code"], {"fast_ma": 7, "slow_ma": 30})
    plots = signals.attrs["chart_series"]
    assert [p["label"] for p in plots] == ["策略 MA7", "策略 MA30"]
    assert plots[0]["values"][:6] == [None] * 6
    pd.testing.assert_series_equal(
        pd.Series(plots[0]["values"]), sample_bars.close.rolling(7).mean(), check_names=False
    )
    assert set(signals.columns) == {"date", "signal", "position_target", "reason"}


def test_plots_are_saved_in_run_and_restored_without_execution(tmp_path):
    path = tmp_path / "charts.duckdb"
    with TestClient(create_app(path, start_scheduler=False)) as client:
        query = {"symbol": "000938", "source": "sample", "start_date": "2023-01-01", "end_date": "2024-01-01"}
        assert client.post("/api/data/download", json=query).status_code == 200
        template = PYTHON_EXAMPLES[0]
        definition = {
            "kind": "python",
            "name": "绘图",
            "code": template["code"],
            "parameters": template["parameters"],
        }
        response = client.post("/api/backtest", json={**query, "custom_strategy": definition})
        assert response.status_code == 200, response.text
        result = response.json()
        assert len(result["chart_series"]) == 2
        assert len(result["chart_series"][0]["values"]) == len(result["bars"])
    with TestClient(create_app(path, start_scheduler=False)) as client:
        assert client.get("/api/backtest/" + result["run_id"]).json() == result


def test_future_dependent_plot_rejected_even_if_signals_unchanged(sample_bars):
    code = """
import pandas as pd
def generate_signals(data, params):
    out = pd.DataFrame({"date": data.date, "signal": "NONE", "position_target": 0, "reason": "wait"})
    out["plot_future"] = data.close.shift(-1)
    return out
"""
    with pytest.raises(ValueError, match="历史前缀检查失败"):
        run_python_strategy(sample_bars, code, {})


def test_automatic_plot_columns_and_explicit_panes():
    data = pd.DataFrame({"plot_ma": [None, 2.5], "ignored": [10, 20]})
    plots = chart_output(data)
    assert plots[0]["label"] == "ma" and plots[0]["values"] == [None, 2.5]
    data.attrs["plots"] = [{"column": "ignored", "label": "阈值", "pane": "动量", "color": "#123456"}]
    assert chart_output(data)[0]["pane"] == "动量"
    data.attrs["plots"] = []
    assert chart_output(data) == []


@pytest.mark.parametrize(
    "spec",
    [
        [{"column": "missing"}],
        [{"column": "plot_ma", "color": "red"}],
        [{"column": "plot_ma"}] * 2,
        [{"column": "plot_ma"}] * 21,
    ],
)
def test_invalid_plot_metadata_rejected(spec):
    frame = pd.DataFrame({"plot_ma": [1, 2]})
    frame.attrs["plots"] = copy.deepcopy(spec)
    with pytest.raises(ValueError):
        chart_output(frame)


@pytest.mark.parametrize("values", [[1, float("inf")], ["1", "bad"]])
def test_invalid_plot_values_rejected(values):
    with pytest.raises(ValueError):
        chart_output(pd.DataFrame({"plot_ma": values}))
