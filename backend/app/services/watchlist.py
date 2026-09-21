import logging
from datetime import datetime, timedelta
from threading import Event, Lock, Thread
from zoneinfo import ZoneInfo

from app.data.base import AdjustmentChanged
from app.models.schemas import DataRequest

logger = logging.getLogger(__name__)
SHANGHAI = ZoneInfo("Asia/Shanghai")


def update_target(now: datetime):
    """Only request completed sessions; holidays are handled by the provider's empty result."""
    local = now.astimezone(SHANGHAI)
    target = local.date()
    if local.hour < 18:
        target -= timedelta(days=1)
    while target.weekday() >= 5:
        target -= timedelta(days=1)
    return target


class WatchlistUpdater:
    def __init__(self, repository, market):
        self.repo, self.market = repository, market
        self.stop_event = Event()
        self.run_lock = Lock()
        self.thread = None

    def status(self):
        return {
            "enabled": self.repo.auto_update_enabled(),
            "running": self.run_lock.locked(),
            "schedule": "每天 18:00（北京时间）",
            "target_date": str(update_target(datetime.now(SHANGHAI))),
        }

    def update(self, symbol: str | None = None, automatic: bool = False, now: datetime | None = None):
        if not self.run_lock.acquire(blocking=False):
            return {"running": True, "results": [], "message": "自选股正在更新，请稍后查看"}
        results = []
        try:
            now = now or datetime.now(SHANGHAI)
            target = update_target(now)
            for item in self.repo.saved_stocks():
                if self.stop_event.is_set():
                    break
                if automatic and not self.repo.auto_update_enabled():
                    break
                if item["source"] == "sample" or (symbol and item["symbol"] != symbol):
                    continue
                if automatic and item["checked_at"]:
                    # Persist checks across restarts. Retry unavailable data hourly.
                    same_target = item["target_date"] == str(target)
                    recent = now - datetime.fromisoformat(item["checked_at"]) < timedelta(hours=1)
                    complete = item["status"] in ("success", "refresh_required")
                    if same_target and (recent or complete):
                        continue
                key = {k: item[k] for k in ("symbol", "source", "adjust")}
                try:
                    outcome = self.market.download(
                        DataRequest(
                            **key,
                            start_date=item["start_date"],
                            end_date=max(str(target), item["start_date"]),
                        ),
                        incremental=True,
                    )
                    status = "success" if outcome["last_date"] >= str(target) else "waiting"
                    message = outcome["message"]
                except AdjustmentChanged as exc:
                    status, message = "refresh_required", str(exc)
                    outcome = {"rows_written": 0}
                except Exception as exc:
                    logger.exception("Watchlist update failed for %s", key)
                    status, message = "error", str(exc)
                    outcome = {"rows_written": 0}
                self.repo.record_market_update(
                    item["symbol"],
                    item["adjust"],
                    item["source"],
                    now.isoformat(),
                    target,
                    status,
                    message,
                )
                results.append({**key, **outcome, "status": status, "message": message})
            failures = sum(r["status"] in ("error", "refresh_required") for r in results)
            rows = sum(r["rows_written"] for r in results)
            return {
                "running": False,
                "results": results,
                "message": f"已检查 {len(results)} 份行情，新增 {rows} 根日 K"
                + (f"；{failures} 份需处理，请查看侧栏提示" if failures else ""),
            }
        finally:
            self.run_lock.release()

    def start(self):
        self.thread = Thread(target=self._loop, name="watchlist-updater", daemon=True)
        self.thread.start()

    def _loop(self):
        while not self.stop_event.is_set():
            try:
                if self.repo.auto_update_enabled():
                    self.update(automatic=True)
                if self.market is not None and not self.stop_event.is_set():
                    self.market.fill_stock_names()
            except Exception:
                logger.exception("Automatic market update failed")
            self.stop_event.wait(60)

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join()
