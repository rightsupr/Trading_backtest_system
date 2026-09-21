import logging
import math
from datetime import timedelta
from threading import RLock
from time import monotonic

from app.data.base import AdjustmentChanged, ProviderError, validate_bars
from app.data.eastmoney import EastMoneyProvider
from app.data.sample import SampleProvider
from app.data.tencent import TencentProvider
from app.models.schemas import DataRequest

logger = logging.getLogger(__name__)


class MarketService:
    def __init__(self, repository, providers=None):
        self.repo = repository
        self.providers = providers or {
            "eastmoney": EastMoneyProvider(),
            "tencent": TencentProvider(),
            "sample": SampleProvider(),
        }
        self.lock = RLock()
        self.name_attempts = {}

    def fill_stock_names(self):
        provider = self.providers.get("tencent")
        if not hasattr(provider, "get_stock_names"):
            return
        now = monotonic()
        symbols = sorted(
            {
                s["symbol"]
                for s in self.repo.saved_stocks()
                if s["source"] != "sample"
                and (not s["name"] or s["name"] == s["symbol"])
                and now - self.name_attempts.get(s["symbol"], float("-inf")) >= 3600
            }
        )
        if not symbols:
            return
        self.name_attempts.update(dict.fromkeys(symbols, now))
        try:
            self.repo.save_stock_names(provider.get_stock_names(symbols))
        except Exception:
            logger.warning("Stock names unavailable; existing names and bars are preserved", exc_info=True)

    def download(self, request: DataRequest, incremental: bool = False) -> dict:
        with self.lock:
            return self._download(request, incremental)

    def _download(self, req: DataRequest, incremental: bool) -> dict:
        provider = self.providers[req.source]
        first, last = self.repo.bounds(req.symbol, req.adjust, req.source)
        start, end = req.start_date, req.end_date
        if req.force_refresh and first:
            # A refresh must cover the entire cached adjustment series, avoiding mixed bases.
            start, end = min(start, first), max(end, last)
        elif incremental and last:
            start = last + timedelta(days=1)
        if start > end:
            return {"rows_written": 0, "message": "本地行情已覆盖所选结束日期", "last_date": str(last)}
        logger.info("Download %s %s %s %s..%s", req.source, req.symbol, req.adjust, start, end)
        frame = validate_bars(provider.get_daily_bars(req.symbol, start, end, req.adjust))
        if not frame.empty:
            frame = frame[(frame.date >= start) & (frame.date <= end)]
        if frame.empty:
            if last and incremental and not req.force_refresh:
                return {"rows_written": 0, "message": "数据源暂无新的交易日行情", "last_date": str(last)}
            raise ProviderError("没有返回行情：请检查股票代码、上市日期或时间范围")
        if last and req.adjust != "raw" and not req.force_refresh and req.source != "sample":
            # One historical anchor is checked; full history is not redownloaded on ordinary updates.
            anchor = provider.get_daily_bars(req.symbol, last, last, req.adjust)
            local = self.repo.bars(req.symbol, last, last, req.adjust, req.source)
            if anchor.empty or not math.isclose(
                float(anchor.iloc[-1].close), float(local.iloc[-1].close), abs_tol=0.011
            ):
                raise AdjustmentChanged("复权历史基准已变化或无法校验，请点击「完整刷新」重建这一复权版本")
        count = self.repo.upsert_bars(
            req.symbol, req.adjust, req.source, frame, replace=(start, end) if req.force_refresh else None
        )
        logger.info("Stored %s rows for %s", count, req.symbol)
        return {
            "rows_written": count,
            "message": f"已写入 {count} 根日 K",
            "last_date": str(frame.date.max()),
            "fetched_start": str(start),
            "fetched_end": str(end),
        }
