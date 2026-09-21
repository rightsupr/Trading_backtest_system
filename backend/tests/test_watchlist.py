from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.data.base import ProviderError
from app.data.sample import SampleProvider
from app.database.repository import Repository
from app.main import create_app
from app.models.schemas import DataRequest
from app.services.market import MarketService
from app.services.watchlist import SHANGHAI, WatchlistUpdater, update_target


class RecordingProvider(SampleProvider):
    def __init__(self):
        self.calls = []
        self.fail = set()
        self.changed = False
        self.empty = False

    def get_daily_bars(self, symbol, start_date, end_date, adjust):
        self.calls.append((symbol, start_date, end_date, adjust))
        if symbol in self.fail:
            raise ProviderError("测试网络失败")
        frame = super().get_daily_bars(symbol, start_date, end_date, adjust)
        if self.changed:
            frame[["open", "high", "low", "close"]] *= 0.9
        return frame.iloc[:0] if self.empty else frame


def seed(repo, symbol="000938", source="tencent", adjust="raw"):
    frame = SampleProvider().get_daily_bars(symbol, date(2024, 1, 1), date(2024, 1, 10), adjust)
    repo.upsert_bars(symbol, adjust, source, frame)


NOW = datetime(2024, 1, 15, 18, 1, tzinfo=SHANGHAI)


@pytest.mark.parametrize(
    ("time", "expected"),
    [
        ("2024-01-15T17:59:00+08:00", "2024-01-12"),
        ("2024-01-15T18:00:00+08:00", "2024-01-15"),
        ("2024-01-14T19:00:00+08:00", "2024-01-12"),
        ("2024-01-15T10:00:00+00:00", "2024-01-15"),
    ],
)
def test_schedule_uses_shanghai_completed_weekdays(time, expected):
    assert str(update_target(datetime.fromisoformat(time))) == expected


def test_existing_data_discovered_and_settings_survive_restart(repository):
    seed(repository)
    seed(repository, "002396")
    seed(repository, source="eastmoney", adjust="qfq")
    repository.set_auto_update(False)
    restored = Repository(repository.path)
    assert not restored.auto_update_enabled()
    stocks = restored.saved_stocks()
    assert len(stocks) == 3
    assert {s["symbol"] for s in stocks} == {"000938", "002396"}
    assert all(s["end_date"] == "2024-01-10" and s["bars"] == 8 for s in stocks)


def test_update_all_is_incremental_persistent_and_excludes_sample(repository):
    seed(repository)
    seed(repository, "002396", adjust="qfq")
    seed(repository, source="sample")
    provider = RecordingProvider()
    market = MarketService(repository, {"tencent": provider})
    updater = WatchlistUpdater(repository, market)
    outcome = updater.update(automatic=True, now=NOW)
    assert len(outcome["results"]) == 2
    assert all(r["status"] == "success" and r["rows_written"] == 3 for r in outcome["results"])
    assert provider.calls[0][1] == date(2024, 1, 11)
    assert repository.bounds("000938", "raw", "sample")[1] == date(2024, 1, 10)
    assert (
        WatchlistUpdater(Repository(repository.path), market).update(automatic=True, now=NOW)["results"] == []
    )
    count = len(provider.calls)
    updater.update(now=NOW)
    assert len(provider.calls) == count  # Already-current caches never refetch history.


def test_failure_does_not_block_other_stocks_and_retries_hourly(repository):
    seed(repository)
    seed(repository, "002396")
    provider = RecordingProvider()
    provider.fail.add("000938")
    updater = WatchlistUpdater(repository, MarketService(repository, {"tencent": provider}))
    results = updater.update(automatic=True, now=NOW)["results"]
    assert [r["status"] for r in results] == ["error", "success"]
    assert repository.bounds("000938", "raw", "tencent")[1] == date(2024, 1, 10)
    assert updater.update(automatic=True, now=NOW + timedelta(minutes=30))["results"] == []
    provider.fail.clear()
    assert updater.update(automatic=True, now=NOW + timedelta(hours=1))["results"][0]["status"] == "success"


def test_empty_response_not_claimed_current_and_can_retry(repository):
    seed(repository)
    provider = RecordingProvider()
    provider.empty = True
    updater = WatchlistUpdater(repository, MarketService(repository, {"tencent": provider}))
    assert updater.update(now=NOW)["results"][0]["status"] == "waiting"
    assert repository.saved_stocks()[0]["end_date"] == "2024-01-10"
    provider.empty = False
    assert updater.update(automatic=True, now=NOW + timedelta(hours=1))["results"][0]["status"] == "success"


def test_adjustment_change_requires_refresh_and_refresh_clears_error(repository):
    seed(repository, adjust="qfq")
    provider = RecordingProvider()
    provider.changed = True
    market = MarketService(repository, {"tencent": provider})
    updater = WatchlistUpdater(repository, market)
    assert updater.update(now=NOW)["results"][0]["status"] == "refresh_required"
    assert repository.bounds("000938", "qfq", "tencent")[1] == date(2024, 1, 10)
    market.download(
        DataRequest(
            symbol="000938",
            source="tencent",
            adjust="qfq",
            start_date="2024-01-01",
            end_date="2024-01-15",
            force_refresh=True,
        )
    )
    assert repository.saved_stocks()[0]["status"] is None


def test_disabled_auto_still_allows_manual_and_prevents_overlapping_updates(repository):
    seed(repository)
    repository.set_auto_update(False)
    updater = WatchlistUpdater(repository, MarketService(repository, {"tencent": RecordingProvider()}))
    assert updater.update(automatic=True, now=NOW)["results"] == []
    with updater.run_lock:
        assert updater.update(now=NOW)["running"]
    assert updater.update(now=NOW)["results"][0]["rows_written"] == 3


def test_single_stock_updates_its_versions_only(repository):
    seed(repository)
    seed(repository, source="eastmoney", adjust="qfq")
    seed(repository, "002396")
    provider = RecordingProvider()
    updater = WatchlistUpdater(
        repository, MarketService(repository, {"tencent": provider, "eastmoney": provider})
    )
    results = updater.update(symbol="000938", now=NOW)["results"]
    assert len(results) == 2 and all(r["symbol"] == "000938" for r in results)
    assert repository.bounds("002396", "raw", "tencent")[1] == date(2024, 1, 10)


def test_scheduler_runs_on_start_and_stops(repository):
    from threading import Event

    ran = Event()
    updater = WatchlistUpdater(repository, None)
    updater.update = lambda **kwargs: ran.set()
    updater.start()
    try:
        assert ran.wait(timeout=2)
    finally:
        updater.stop()
    assert not updater.thread.is_alive()


def test_names_are_backfilled_once_and_survive_bar_updates(repository):
    class NamedProvider(RecordingProvider):
        def get_stock_names(self, symbols):
            self.calls.append(symbols)
            return {"000938": "紫光股份"}

    seed(repository)
    seed(repository, "002396", source="sample")
    provider = NamedProvider()
    market = MarketService(repository, {"tencent": provider})
    market.fill_stock_names()
    assert provider.calls == [["000938"]]
    assert repository.saved_stocks()[0]["name"] == "紫光股份"
    seed(repository)
    assert repository.saved_stocks()[0]["name"] == "紫光股份"
    market.fill_stock_names()
    assert provider.calls == [["000938"]]


def test_name_lookup_failure_preserves_bars_and_throttles_retry(repository):
    class FailingNames(RecordingProvider):
        def get_stock_names(self, symbols):
            self.calls.append(symbols)
            raise ProviderError("名称暂不可用")

    seed(repository)
    provider = FailingNames()
    market = MarketService(repository, {"tencent": provider})
    market.fill_stock_names()
    market.fill_stock_names()
    assert provider.calls == [["000938"]]
    assert repository.saved_stocks()[0]["bars"] == 8


def test_stock_name_parser_ignores_empty_and_unrequested_symbols(monkeypatch):
    from app.data.tencent import TencentProvider

    class Response:
        text = 'v_sz000938="51~紫光股份~000938~1";\nv_sz002396="51~星网锐捷~002396~1";\nv_pv_none_match="1";'

        def raise_for_status(self):
            pass

    monkeypatch.setattr("app.data.tencent.requests.get", lambda *args, **kwargs: Response())
    assert TencentProvider().get_stock_names(["000938"]) == {"000938": "紫光股份"}


def test_watchlist_api_selection_and_strategy_reuse(tmp_path):
    path = tmp_path / "api.duckdb"
    provider = RecordingProvider()
    with TestClient(create_app(path, {"sample": provider}, start_scheduler=False)) as client:
        assert client.get("/api/watchlist").json()["stocks"] == []
        for symbol in ("000938", "002396"):
            body = {
                "symbol": symbol,
                "start_date": "2023-01-01",
                "end_date": "2024-01-15",
                "source": "sample",
            }
            assert client.post("/api/data/download", json=body).status_code == 200
            run = client.post(
                "/api/backtest",
                json={**body, "strategy_name": "ma_cross", "parameters": {"fast_ma": 5, "slow_ma": 20}},
            ).json()
            assert run["request"]["symbol"] == symbol
            assert run["request"]["parameters"] == {"fast_ma": 5, "slow_ma": 20}
        assert len(client.get("/api/watchlist").json()["stocks"]) == 2
        assert client.post("/api/watchlist/settings", json={"enabled": False}).json()["enabled"] is False
        assert client.post("/api/watchlist/update", json={"symbol": "invalid"}).status_code == 422
        assert client.post("/api/watchlist/update", json={"symbol": "999999"}).status_code == 404
        assert client.post("/api/watchlist/update", json={}).json()["results"] == []
    with TestClient(create_app(path, start_scheduler=False)) as client:
        assert len(client.get("/api/watchlist").json()["stocks"]) == 2
        assert client.get("/api/watchlist").json()["enabled"] is False
