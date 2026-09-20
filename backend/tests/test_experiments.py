import json

import duckdb
import pytest
from fastapi.testclient import TestClient

from app.database.experiments import Experiments
from app.database.repository import Repository
from app.main import create_app


def seed(repo, identifier):
    result = {
        "run_id": identifier,
        "strategy_version": "1",
        "reason": "中文快照",
        "request": {
            "symbol": "000938",
            "strategy_name": "ma_cross",
            "parameters": {},
            "start_date": "2024-01-01",
            "end_date": "2024-12-31",
            "config": {"initial_cash": 100000},
        },
        "signals": [{"date": "2024-01-01", "signal": "BUY", "position_target": 1, "reason": "测试"}],
        "trades": [
            {
                "trade_id": f"trade-{identifier}",
                "entry_date": "2024-01-01",
                "exit_date": "2024-01-02",
                "entry_price": 10,
                "exit_price": 11,
                "shares": 100,
                "profit": 100,
            }
        ],
        "equity": [
            {
                "date": "2024-01-01",
                "cash": 99000,
                "position_value": 1000,
                "total_equity": 100000,
                "drawdown": 0,
            }
        ],
    }
    repo.save_run(result)
    return result


def test_favorite_persists_without_changing_snapshot(repository):
    snapshot = seed(repository, "one")
    store = Experiments(repository)
    assert store.list()["items"][0]["is_favorite"] is False
    assert store.favorite("one", True)["is_favorite"] is True
    reopened = Repository(repository.path)
    assert Experiments(reopened).list(favorites=True)["total"] == 1
    assert reopened.get_run("one") == snapshot
    assert store.favorite("missing", True) is None
    store.favorite("one", False)
    assert store.list(favorites=True)["total"] == 0


def test_existing_database_migration_and_storage(repository):
    snapshot = seed(repository, "old")
    with repository.connection() as conn:
        conn.execute("DROP TABLE experiment_metadata")
    repo = Repository(repository.path)
    result = Experiments(repo).list()
    expected = len(json.dumps(snapshot, allow_nan=False).encode("utf-8"))
    assert result["items"][0]["snapshot_bytes"] == expected
    assert result["storage"]["snapshot_bytes"] == expected
    assert result["storage"]["database_bytes"] == repo.path.stat().st_size
    assert (
        result["storage"]["total_bytes"]
        == result["storage"]["database_bytes"] + result["storage"]["wal_bytes"]
    )
    assert repo.get_run("old") == snapshot


def test_delete_cleans_children_and_protects_shared_data(repository, sample_bars):
    repository.upsert_bars("000938", "raw", "sample", sample_bars)
    definition = repository.save_definition({"name": "策略", "kind": "rules"}, "hash")
    for identifier in ("one", "two", "keep"):
        seed(repository, identifier)
    store = Experiments(repository)
    store.favorite("keep", True)
    result = store.delete(["one", "one", "keep", "missing", "two"])
    assert result == {"deleted_ids": ["one", "two"], "protected_ids": ["keep"], "missing_ids": ["missing"]}
    with repository.connection() as conn:
        for table in ("strategy_runs", "signals", "trades", "equity_curve", "experiment_metadata"):
            assert conn.execute(f"SELECT DISTINCT run_id FROM {table}").fetchall() == [("keep",)]
        assert conn.execute("SELECT count(*) FROM daily_bars").fetchone()[0] == len(sample_bars)
    assert repository.get_definition(definition["definition_id"]) == definition
    store.favorite("keep", False)
    assert store.delete(["keep"])["deleted_ids"] == ["keep"]
    assert store.list()["storage"]["snapshot_bytes"] == 0
    assert store.list()["items"] == []


def test_failed_delete_rolls_back_children(repository):
    seed(repository, "one")
    with repository.connection() as conn:
        conn.execute("CREATE TABLE retained (run_id VARCHAR REFERENCES strategy_runs(run_id))")
        conn.execute("INSERT INTO retained VALUES ('one')")
    with pytest.raises(duckdb.ConstraintException):
        Experiments(repository).delete(["one"])
    with repository.connection() as conn:
        for table in ("strategy_runs", "signals", "trades", "equity_curve"):
            assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 1


def test_pagination_reaches_older_than_one_hundred(repository):
    seed(repository, "first")
    with repository.connection() as conn:
        conn.execute(
            "INSERT INTO strategy_runs SELECT 'extra-' || n, symbol, strategy_name, strategy_version, "
            "parameters_json, start_date, end_date, initial_cash, created_at, result_json "
            "FROM strategy_runs CROSS JOIN range(105) t(n)"
        )
    store = Experiments(repository)
    pages = [store.list(page=p) for p in range(1, 7)]
    assert pages[0]["total"] == 106
    assert len({r["run_id"] for page in pages for r in page["items"]}) == 106
    assert store.list(page=99)["page"] == 6
    store.favorite("first", True)
    assert store.list(favorites=True)["items"][0]["run_id"] == "first"


def test_api_validation_protection_and_deletion(tmp_path):
    app = create_app(tmp_path / "api.duckdb")
    with TestClient(app) as client:
        seed(app.state.repo, "one")
        seed(app.state.repo, "two")
        assert client.get("/api/experiments?page=0").status_code == 422
        assert client.post("/api/experiments/delete", json={"run_ids": []}).status_code == 422
        assert client.post("/api/experiments/delete", json={"run_ids": ["a"] * 101}).status_code == 422
        assert client.post("/api/experiments/one/favorite", json={"is_favorite": "false"}).status_code == 422
        assert client.post("/api/experiments/missing/favorite", json={"is_favorite": True}).status_code == 404
        assert (
            client.post(
                "/api/experiments/delete",
                json={"run_ids": ["one"]},
                headers={"origin": "https://example.com"},
            ).status_code
            == 403
        )
        assert client.post("/api/experiments/one/favorite", json={"is_favorite": True}).status_code == 200
        assert client.get("/api/experiments?favorites=true").json()["total"] == 1
        result = client.post("/api/experiments/delete", json={"run_ids": ["one", "two"]}).json()
        assert result["deleted_ids"] == ["two"] and result["protected_ids"] == ["one"]
        assert client.get("/api/backtest/two").status_code == 404
        assert client.get("/api/backtest/one").status_code == 200
