import copy

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.indicators.technical import chart_indicators
from app.main import create_app
from app.models.strategy import RuleDefinition, StrategyDefinition
from app.strategies.contracts import validate_signals
from app.strategies.python_runner import check_python_syntax, run_python_strategy
from app.strategies.rules import generate_rule_signals, operand_series
from app.strategies.templates import PYTHON_EXAMPLES


def rules_definition():
    return {
        "kind": "rules",
        "name": "我的均线策略",
        "rules": {
            "buy": {
                "match": "all",
                "conditions": [
                    {
                        "left": {"feature": "sma", "period": 5},
                        "operator": "cross_up",
                        "right": {"feature": "sma", "period": 20},
                    }
                ],
            },
            "sell": {
                "match": "any",
                "conditions": [
                    {
                        "left": {"feature": "sma", "period": 5},
                        "operator": "cross_down",
                        "right": {"feature": "sma", "period": 20},
                    }
                ],
            },
        },
    }


def python_definition(index=0):
    example = PYTHON_EXAMPLES[index]
    return {"kind": "python", **{key: example[key] for key in ["name", "description", "code", "parameters"]}}


def test_rules_match_python_template_and_are_causal(sample_bars):
    data = chart_indicators(sample_bars)
    definition = StrategyDefinition.model_validate(rules_definition())
    result = validate_signals(generate_rule_signals(data, definition.rules), data)
    python = run_python_strategy(data, PYTHON_EXAMPLES[0]["code"], PYTHON_EXAMPLES[0]["parameters"])
    pd.testing.assert_frame_equal(
        result[["date", "signal", "position_target"]],
        python[["date", "signal", "position_target"]],
        check_dtype=False,
    )
    pd.testing.assert_frame_equal(result.iloc[:200], generate_rule_signals(data.iloc[:200], definition.rules))
    assert "当前" in result[result.signal == "BUY"].iloc[0].reason


def test_rule_offsets_slopes_and_consecutive():
    from app.models.strategy import Operand

    data = pd.DataFrame(
        {"date": pd.bdate_range("2025-01-01", periods=5).date, "close": [1.0, 2.0, 3.0, 4.0, 5.0]}
    )
    op = Operand(feature="close", slope_period=2, offset=1)
    assert operand_series(data, op).iloc[3] == 1
    rules = RuleDefinition.model_validate(
        {
            "buy": {
                "conditions": [
                    {
                        "left": {"feature": "close"},
                        "operator": "gt",
                        "right": {"feature": "constant", "value": 1},
                        "consecutive": 2,
                    }
                ]
            },
            "sell": {
                "conditions": [
                    {
                        "left": {"feature": "close"},
                        "operator": "gt",
                        "right": {"feature": "constant", "value": 4},
                    }
                ]
            },
        }
    )
    assert generate_rule_signals(data, rules).signal.tolist() == ["NONE", "NONE", "BUY", "HOLD", "SELL"]


def test_exit_priority_when_both_rules_match(sample_bars):
    body = rules_definition()
    always = {
        "conditions": [
            {
                "left": {"feature": "constant", "value": 1},
                "operator": "gt",
                "right": {"feature": "constant", "value": 0},
            }
        ]
    }
    body["rules"] = {"buy": always, "sell": always}
    signals = generate_rule_signals(
        chart_indicators(sample_bars), StrategyDefinition.model_validate(body).rules
    )
    assert signals.signal.eq("NONE").all()


def test_rules_reject_invalid_period_and_empty_group():
    body = rules_definition()
    body["rules"]["buy"]["conditions"][0]["left"]["offset"] = -1
    with pytest.raises(ValueError):
        StrategyDefinition.model_validate(body)
    body = rules_definition()
    body["rules"]["sell"]["conditions"] = []
    with pytest.raises(ValueError):
        StrategyDefinition.model_validate(body)


def test_python_errors_are_readable_and_time_bounded(sample_bars):
    data = chart_indicators(sample_bars.iloc[:50])
    with pytest.raises(ValueError, match="第 1 行语法错误"):
        check_python_syntax("def generate_signals(:")
    with pytest.raises(ValueError, match="入口函数"):
        check_python_syntax("x = 1")
    with pytest.raises(ValueError, match="第 2 行.*ZeroDivisionError"):
        run_python_strategy(data, "def generate_signals(data, params):\n    return 1 / 0", {})
    with pytest.raises(ValueError, match="必须返回"):
        run_python_strategy(data, "def generate_signals(data, params):\n    return []", {})
    with pytest.raises(ValueError, match="已终止"):
        run_python_strategy(data, "def generate_signals(data, params):\n    while True: pass", {}, timeout=1)


def test_python_rejects_future_data_and_inconsistent_targets(sample_bars):
    data = chart_indicators(sample_bars.iloc[:50])
    leaking = """import pandas as pd
def generate_signals(data, params):
    rows = [{"date": d, "signal": "NONE", "position_target": 0, "reason": str(len(data))} for d in data.date]
    return pd.DataFrame(rows)
"""
    with pytest.raises(ValueError, match="历史前缀检查失败"):
        run_python_strategy(data, leaking, {})
    bad = leaking.replace('"NONE"', '"BUY"')
    with pytest.raises(ValueError, match="不一致"):
        run_python_strategy(data, bad, {})


def test_python_slope_example(sample_bars):
    example = PYTHON_EXAMPLES[1]
    result = run_python_strategy(chart_indicators(sample_bars), example["code"], example["parameters"])
    assert len(result) == len(sample_bars)
    assert result.signal.eq("BUY").any()


def test_editor_api_versions_and_snapshot_survive_restart(tmp_path):
    path = tmp_path / "editor.duckdb"
    body = {"symbol": "000938", "start_date": "2023-01-01", "end_date": "2024-12-31", "source": "sample"}
    with TestClient(create_app(path)) as client:
        assert len(client.get("/api/strategy-editor/examples").json()) == 2
        definition = rules_definition()
        first = client.post("/api/strategy-editor/definitions", json={"definition": definition}).json()
        assert first["revision"] == 1
        assert client.post("/api/data/download", json=body).status_code == 200
        custom_body = {**body, "custom_strategy": definition}
        validation = client.post("/api/strategy-editor/validate", json=custom_body)
        assert validation.status_code == 200, validation.text
        assert validation.json()["signal_counts"]["BUY"] > 0
        assert client.get("/api/backtest").json() == []
        result = client.post("/api/backtest", json=custom_body)
        assert result.status_code == 200, result.text
        result = result.json()
        assert len(result["trades"]) > 0
        assert result["request"]["strategy_name"] == definition["name"]
        changed = copy.deepcopy(definition)
        changed["rules"]["buy"]["conditions"][0]["left"]["period"] = 8
        second = client.post(
            "/api/strategy-editor/definitions",
            json={"definition": changed, "parent_id": first["definition_id"]},
        ).json()
        assert second["revision"] == 2 and second["definition_id"] != first["definition_id"]
        assert second["content_hash"] != first["content_hash"]
        python = python_definition()
        saved = client.post("/api/strategy-editor/definitions", json={"definition": python})
        assert saved.status_code == 200
        run = client.post("/api/backtest", json={**body, "custom_strategy": python})
        assert run.status_code == 200, run.text
        assert run.json()["request"]["custom_strategy"]["code"] == python["code"]
        assert run.json()["strategy_version"] == saved.json()["content_hash"]
        assert client.get("/api/strategy-editor/definitions/missing").status_code == 404
    with TestClient(create_app(path)) as client:
        assert len(client.get("/api/strategy-editor/definitions").json()) == 3
        assert client.get("/api/strategy-editor/definitions/" + first["definition_id"]).json() == first
        assert client.get("/api/backtest/" + result["run_id"]).json() == result


def test_save_checks_syntax_without_executing(tmp_path):
    with TestClient(create_app(tmp_path / "syntax.duckdb")) as client:
        definition = python_definition()
        definition["code"] = (
            "raise RuntimeError('must not execute on save')\ndef generate_signals(data, params):\n    return data"
        )
        assert (
            client.post("/api/strategy-editor/definitions", json={"definition": definition}).status_code
            == 200
        )
        definition["code"] = "def generate_signals(:"
        error = client.post("/api/strategy-editor/definitions", json={"definition": definition})
        assert error.status_code == 422 and "语法错误" in error.json()["detail"]


def test_external_browser_origin_cannot_submit_python(tmp_path):
    with TestClient(create_app(tmp_path / "origin.duckdb")) as client:
        response = client.post(
            "/api/strategy-editor/definitions",
            json={"definition": python_definition()},
            headers={"Origin": "https://external.example"},
        )
        assert response.status_code == 403
        response = client.get("/api/health", headers={"Host": "external.example"})
        assert response.status_code == 400


@pytest.mark.parametrize("definition_factory", [rules_definition, python_definition])
def test_delete_strategy_version_preserves_snapshot_and_revision_sequence(tmp_path, definition_factory):
    path = tmp_path / "delete.duckdb"
    definition = definition_factory()
    prefix = "/api/strategy-editor/definitions"
    with TestClient(create_app(path, start_scheduler=False)) as client:
        first = client.post(prefix, json={"definition": definition}).json()
        second = client.post(
            prefix, json={"definition": definition, "parent_id": first["definition_id"]}
        ).json()
        body = {"symbol": "000938", "source": "sample", "start_date": "2023-01-01", "end_date": "2024-12-31"}
        client.post("/api/data/download", json=body)
        result = client.post("/api/backtest", json={**body, "custom_strategy": definition})
        assert result.status_code == 200
        snapshot = result.json()
        deletion = f"{prefix}/{second['definition_id']}/delete"
        assert (
            client.post(deletion, json={}, headers={"origin": "https://untrusted.example"}).status_code == 403
        )
        assert client.get(f"{prefix}/{second['definition_id']}").status_code == 200
        assert client.post(deletion, json={}).status_code == 200
        assert client.post(deletion, json={}).status_code == 404
        assert client.get(f"{prefix}/{second['definition_id']}").status_code == 404
        assert len(client.get(prefix).json()) == 1
        assert client.get(f"/api/backtest/{snapshot['run_id']}").json() == snapshot
        assert (
            client.post(
                prefix, json={"definition": definition, "parent_id": second["definition_id"]}
            ).status_code
            == 422
        )
        third = client.post(
            prefix, json={"definition": definition, "parent_id": first["definition_id"]}
        ).json()
        assert third["revision"] == 3
    with TestClient(create_app(path, start_scheduler=False)) as client:
        assert len(client.get(prefix).json()) == 2
        assert client.get(f"{prefix}/{second['definition_id']}").status_code == 404
        assert client.get(f"/api/backtest/{snapshot['run_id']}").json() == snapshot


def test_strategy_deletion_migrates_old_database(tmp_path):
    import duckdb

    from app.database.repository import Repository

    path = tmp_path / "legacy.duckdb"
    repo = Repository(path)
    first = repo.save_definition(rules_definition(), "legacy-hash")
    with duckdb.connect(str(path)) as conn:
        conn.execute("ALTER TABLE strategy_definitions DROP COLUMN deleted")
    restored = Repository(path)
    assert restored.get_definition(first["definition_id"]) == first
    assert restored.delete_definition(first["definition_id"])
    assert restored.list_definitions() == []
