from datetime import date, datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from app.data.base import BaseMarketDataProvider, ProviderError, validate_bars


class TencentProvider(BaseMarketDataProvider):
    """Independent real-data alternative. Never merges with EastMoney cache."""

    name = "tencent"

    def get_daily_bars(self, symbol: str, start_date: date, end_date: date, adjust: str) -> pd.DataFrame:
        prefix = "sh" if symbol.startswith(("6", "9")) else "bj" if symbol.startswith(("4", "8")) else "sz"
        code = prefix + symbol
        adjustment = "" if adjust == "raw" else adjust
        rows = []
        try:
            # <= one year per page: the upstream silently caps requests at 640 bars.
            for year in range(
                start_date.year, min(end_date.year, datetime.now(ZoneInfo("Asia/Shanghai")).year) + 1
            ):
                start = max(start_date, date(year, 1, 1))
                end = min(end_date, date(year, 12, 31))
                query = urlencode({"param": f"{code},day,{start},{end},640,{adjustment}"}, safe=",")
                response = requests.get(
                    "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?" + query, timeout=20
                )
                response.raise_for_status()
                payload = response.json()
                if payload.get("code") != 0:
                    raise ValueError("腾讯接口未返回成功状态")
                series = payload.get("data", {}).get(code, {})
                items = series.get(f"{adjustment}day", series.get("day", []))
                rows.extend([item[:6] for item in items])
            if not rows:
                return pd.DataFrame()
            data = pd.DataFrame(rows, columns=["date", "open", "close", "high", "low", "volume"])
            # This endpoint returns lots for ordinary stocks; STAR board uses shares.
            data["volume"] = pd.to_numeric(data["volume"]) * (1 if code.startswith("sh688") else 100)
            frame = validate_bars(data)
            frame["pre_close"] = frame.close.shift(1)
            frame["change"] = frame.close - frame.pre_close
            frame["pct_change"] = (frame.close / frame.pre_close - 1) * 100
            return frame[(frame.date >= start_date) & (frame.date <= end_date)].reset_index(drop=True)
        except Exception as exc:
            raise ProviderError("腾讯行情请求失败，请检查股票代码和网络后重试") from exc
