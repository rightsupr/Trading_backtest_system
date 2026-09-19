import logging
from datetime import date
from urllib.parse import urlencode

import pandas as pd
import requests

from app.data.base import BaseMarketDataProvider, ProviderError, validate_bars

logger = logging.getLogger(__name__)


class EastMoneyProvider(BaseMarketDataProvider):
    name = "eastmoney"

    def get_daily_bars(self, symbol: str, start_date: date, end_date: date, adjust: str) -> pd.DataFrame:
        # AKShare is deliberately confined to the concrete provider.
        import akshare as ak

        try:
            frame = ak.stock_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=start_date.strftime("%Y%m%d"),
                end_date=end_date.strftime("%Y%m%d"),
                adjust="" if adjust == "raw" else adjust,
                timeout=20,
            )
        except Exception as exc:  # noqa: BLE001 -- upstream library failures use same-source fallback
            logger.warning("AKShare request failed for %s; trying direct EastMoney endpoint: %s", symbol, exc)
            return self._direct(symbol, start_date, end_date, adjust)
        if frame is None or frame.empty:
            return pd.DataFrame()
        frame = frame.rename(
            columns={
                "日期": "date",
                "开盘": "open",
                "最高": "high",
                "最低": "low",
                "收盘": "close",
                "成交量": "volume",
                "成交额": "amount",
                "换手率": "turnover",
                "涨跌额": "change",
                "涨跌幅": "pct_change",
            }
        )
        frame["volume"] = pd.to_numeric(frame["volume"]) * 100  # source unit: lots
        frame["pre_close"] = frame["close"] - frame["change"]
        return validate_bars(frame)

    def _direct(self, symbol: str, start_date: date, end_date: date, adjust: str) -> pd.DataFrame:
        """Same real data source, alternate request format for upstream compatibility."""
        try:
            query = urlencode(
                {
                    "secid": f"{1 if symbol.startswith(('6', '9')) else 0}.{symbol}",
                    "klt": "101",
                    "fqt": {"raw": "0", "qfq": "1", "hfq": "2"}[adjust],
                    "beg": start_date.strftime("%Y%m%d"),
                    "end": end_date.strftime("%Y%m%d"),
                    "fields1": "f1,f2,f3,f4,f5,f6",
                    "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                },
                safe=",",
            )
            response = requests.get(
                "https://push2his.eastmoney.com/api/qt/stock/kline/get?" + query, timeout=20
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("rc", 0) != 0:
                raise ValueError("upstream rejected request")
            data = payload.get("data")
            if not data or not data.get("klines"):
                return pd.DataFrame()
            frame = pd.DataFrame(
                [row.split(",") for row in data["klines"]],
                columns=[
                    "date",
                    "open",
                    "close",
                    "high",
                    "low",
                    "volume",
                    "amount",
                    "amplitude",
                    "pct_change",
                    "change",
                    "turnover",
                ],
            )
            for field in frame.columns.drop("date"):
                frame[field] = pd.to_numeric(frame[field], errors="coerce")
            frame["volume"] *= 100
            frame["pre_close"] = frame["close"] - frame["change"]
            frame.attrs["stock_name"] = data.get("name", symbol)
            return validate_bars(frame)
        except Exception as exc:
            raise ProviderError("东方财富请求失败，请检查网络后重试；不会以模拟数据替代真实行情") from exc
