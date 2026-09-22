from datetime import date

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.data.base import AdjustmentChanged, ProviderError
from app.data.sample import SampleProvider
from app.main import create_app
from app.models.schemas import DataRequest
from app.services.market import MarketService


def test_duplicate_writes_and_adjust_source_isolation(repository, sample_bars):
    for _ in range(2):
        repository.upsert_bars("000938", "raw", "sample", sample_bars)
    repository.upsert_bars("000938", "qfq", "sample", sample_bars)
    repository.upsert_bars("000938", "raw", "eastmoney", sample_bars)
    with repository.connection() as conn:
        assert conn.execute("SELECT count(*) FROM daily_bars").fetchone()[0] == len(sample_bars) * 3


class SpyProvider(SampleProvider):
    def __init__(self):
        self.calls = []
        self.changed = False

    def get_daily_bars(self, symbol, start_date, end_date, adjust):
        self.calls.append((start_date, end_date))
        data = super().get_daily_bars(symbol, start_date, end_date, adjust)
        if self.changed:
            data["close"] *= 0.99
        return data


def test_incremental_only_fetches_after_latest(repository):
    provider = SpyProvider()
    service = MarketService(repository, {"sample": provider})
    req = DataRequest(symbol="000938", start_date="2024-01-01", end_date="2024-01-10", source="sample")
    service.download(req)
    service.download(req.model_copy(update={"end_date": date(2024, 1, 15)}), incremental=True)
    assert provider.calls[-1][0] == date(2024, 1, 11)
    before = len(provider.calls)
    service.download(req, incremental=True)
    assert len(provider.calls) == before


def test_adjustment_change_rejects_mixed_history(repository):
    provider = SpyProvider()
    service = MarketService(repository, {"eastmoney": provider})
    req = DataRequest(symbol="000938", start_date="2024-01-01", end_date="2024-01-10")
    service.download(req)
    provider.changed = True
    with pytest.raises(AdjustmentChanged):
        service.download(req.model_copy(update={"end_date": date(2024, 1, 15)}), incremental=True)
    assert repository.bounds("000938", "qfq", "eastmoney")[1] == date(2024, 1, 10)


def test_api_roundtrip_and_immutable_runs(tmp_path):
    app = create_app(tmp_path / "api.duckdb")
    with TestClient(app) as client:
        body = {"symbol": "000938", "start_date": "2023-01-01", "end_date": "2025-01-01", "source": "sample"}
        assert client.get("/api/health").status_code == 200
        assert client.post("/api/backtest", json=body).status_code == 422
        assert client.post("/api/data/download", json=body).status_code == 200
        assert (
            len(
                client.get(
                    "/api/stocks/000938/bars", params={k: v for k, v in body.items() if k != "symbol"}
                ).json()["bars"]
            )
            > 400
        )
        result = client.post("/api/backtest", json=body)
        assert result.status_code == 200, result.text
        result = result.json()
        assert len(result["trades"]) > 0
        run_id = result["run_id"]
        assert client.get(f"/api/backtest/{run_id}").json() == result
        assert client.get(f"/api/backtest/{run_id}/trades").json() == result["trades"]
        assert client.get(f"/api/backtest/{run_id}/equity").json() == result["equity"]
        second = client.post("/api/backtest", json={**body, "strategy_name": "macd"}).json()
        assert second["run_id"] != run_id
        assert len(client.get("/api/backtest").json()) == 2
        assert client.get("/api/backtest/missing").status_code == 404
        assert client.post("/api/data/download", json={**body, "symbol": "invalid"}).status_code == 422
        assert (
            client.post(
                "/api/backtest", json={**body, "parameters": {"fast_ma": 30, "slow_ma": 10}}
            ).status_code
            == 422
        )
        assert client.post("/api/data/download", json={**body, "end_date": "2000-01-01"}).status_code == 422


def test_empty_provider_has_actionable_error(repository):
    class Empty(SampleProvider):
        def get_daily_bars(self, *args):
            return pd.DataFrame()

    with pytest.raises(ProviderError, match="没有返回行情"):
        MarketService(repository, {"sample": Empty()}).download(
            DataRequest(symbol="000938", start_date="2024-01-01", end_date="2024-01-02", source="sample")
        )


def test_sample_is_consistent_across_incremental_ranges():
    provider = SampleProvider()
    before = provider.get_daily_bars("000938", date(2024, 1, 1), date(2024, 1, 10), "qfq")
    after = provider.get_daily_bars("000938", date(2024, 1, 1), date(2024, 2, 1), "qfq")
    pd.testing.assert_frame_equal(before, after.iloc[: len(before)])


def test_incremental_accepts_nontrading_start_date(repository):
    provider = SpyProvider()
    service = MarketService(repository, {"sample": provider})
    request = DataRequest(symbol="000938", start_date="2023-12-30", end_date="2024-01-10", source="sample")
    service.download(request)
    service.download(request.model_copy(update={"end_date": date(2024, 1, 15)}), incremental=True)
    assert provider.calls[-1][0] == date(2024, 1, 11)


def test_force_refresh_includes_entire_existing_cache(repository):
    provider = SpyProvider()
    service = MarketService(repository, {"sample": provider})
    request = DataRequest(symbol="000938", start_date="2023-01-01", end_date="2024-01-10", source="sample")
    service.download(request)
    service.download(request.model_copy(update={"start_date": date(2024, 1, 1), "force_refresh": True}))
    assert provider.calls[-1][0] == date(2023, 1, 2)


def test_tencent_paginates_and_preserves_missing_fields(monkeypatch):
    from app.data.tencent import TencentProvider

    calls = []

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            year = 2023 if len(calls) == 1 else 2024
            return {
                "code": 0,
                "data": {"sz000938": {"qfqday": [[f"{year}-06-01", "10", "11", "12", "9", "1000"]]}},
            }

    def fetch(url, **kwargs):
        calls.append(url)
        return Response()

    monkeypatch.setattr("app.data.tencent.requests.get", fetch)
    frame = TencentProvider().get_daily_bars("000938", date(2023, 1, 1), date(2024, 12, 31), "qfq")
    assert len(calls) == 2
    assert len(frame) == 2
    assert frame.iloc[0].volume == 100000
    assert frame.amount.isna().all() and frame.turnover.isna().all()


def test_provider_error_does_not_delete_existing_data(repository, sample_bars):
    repository.upsert_bars("000938", "qfq", "sample", sample_bars)

    class Failing(SampleProvider):
        def get_daily_bars(self, *args):
            raise ProviderError("offline")

    service = MarketService(repository, {"sample": Failing()})
    with pytest.raises(ProviderError):
        service.download(
            DataRequest(
                symbol="000938",
                start_date="2023-01-01",
                end_date="2025-01-01",
                source="sample",
                force_refresh=True,
            )
        )
    assert repository.bounds("000938", "qfq", "sample")[0] == sample_bars.date.min()


def test_execution_modes_saved_and_old_snapshots_preserved(tmp_path):
    with TestClient(create_app(tmp_path / "timing.duckdb", start_scheduler=False)) as client:
        body = {"symbol": "000938", "start_date": "2023-01-01", "end_date": "2024-01-01", "source": "sample"}
        assert client.get("/api/config").json()["execution_timing"] == "execute_same_close"
        assert client.post("/api/data/download", json=body).status_code == 200
        old_response = client.post("/api/backtest", json={
            **body, "config": {"execution_timing": "execute_next_open"},
        })
        assert old_response.status_code == 200, old_response.text
        old = old_response.json()
        response = client.post("/api/backtest", json=body)
        assert response.status_code == 200, response.text
        new = response.json()
        assert new["request"]["config"]["execution_timing"] == "execute_same_close"
        assert new["fills"] and all(f["date"] == f["signal_date"] for f in new["fills"])
        assert old["fills"] and all(f["date"] > f["signal_date"] for f in old["fills"])
        assert any("尾盘近似" in warning for warning in new["warnings"])
        assert client.get(f"/api/backtest/{old['run_id']}").json() == old
        assert client.get(f"/api/backtest/{new['run_id']}").json() == new
