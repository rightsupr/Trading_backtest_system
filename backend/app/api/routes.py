from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.indicators.technical import IndicatorRegistry, chart_indicators
from app.models.schemas import Adjust, BacktestConfig, BacktestRequest, DataRequest, Source
from app.services.research import run_research
from app.services.serialization import records
from app.strategies import STRATEGIES

router = APIRouter(prefix="/api")


class AutoUpdateSettings(BaseModel):
    enabled: bool


class WatchlistUpdateRequest(BaseModel):
    symbol: str | None = Field(default=None, pattern=r"^\d{6}$")


@router.get("/watchlist")
def watchlist(request: Request):
    return {"stocks": request.app.state.repo.saved_stocks(), **request.app.state.watchlist.status()}


@router.post("/watchlist/settings")
def watchlist_settings(body: AutoUpdateSettings, request: Request):
    request.app.state.repo.set_auto_update(body.enabled)
    return request.app.state.watchlist.status()


@router.post("/watchlist/update")
def update_watchlist(body: WatchlistUpdateRequest, request: Request):
    if body.symbol and not any(s["symbol"] == body.symbol for s in request.app.state.repo.saved_stocks()):
        raise HTTPException(404, "请先下载该股票的历史行情")
    return request.app.state.watchlist.update(symbol=body.symbol)


@router.get("/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


@router.get("/config")
def defaults():
    return BacktestConfig().model_dump()


@router.get("/stocks/{symbol}/bars")
def bars(
    request: Request,
    symbol: str,
    start_date: date,
    end_date: date,
    adjust: Adjust = "qfq",
    source: Source = "eastmoney",
):
    query = DataRequest(symbol=symbol, start_date=start_date, end_date=end_date, adjust=adjust, source=source)
    data = request.app.state.repo.bars(query.symbol, start_date, end_date, adjust, source)
    return {
        "symbol": symbol,
        "bars": records(chart_indicators(data)) if not data.empty else [],
        "source": source,
        "adjust": adjust,
    }


@router.post("/data/download")
def download(body: DataRequest, request: Request):
    return request.app.state.market.download(body)


@router.post("/data/update")
def update(body: DataRequest, request: Request):
    return request.app.state.market.download(body, incremental=True)


@router.get("/strategies")
def strategies():
    return [
        {
            "name": s.name,
            "label": s.label,
            "version": s.version,
            "parameters": s.parameter_model.model_json_schema(),
        }
        for s in STRATEGIES.values()
    ]


@router.get("/indicators")
def indicators():
    return {"indicators": IndicatorRegistry.names(), "slope": "(x[t] - x[t-N]) / N"}


@router.post("/backtest")
def backtest(body: BacktestRequest, request: Request):
    return run_research(request.app.state.repo, body)


@router.get("/backtest")
def list_runs(request: Request):
    return request.app.state.repo.list_runs()


def get_result(request: Request, run_id: str):
    result = request.app.state.repo.get_run(run_id)
    if result is None:
        raise HTTPException(404, "未找到该次回测")
    return result


@router.get("/backtest/{run_id}")
def run_result(request: Request, run_id: str):
    return get_result(request, run_id)


@router.get("/backtest/{run_id}/trades")
def run_trades(request: Request, run_id: str):
    return get_result(request, run_id)["trades"]


@router.get("/backtest/{run_id}/equity")
def run_equity(request: Request, run_id: str):
    return get_result(request, run_id)["equity"]


@router.get("/stocks")
def stocks(
    request: Request,
    source: Source = "eastmoney",
    adjust: Adjust = "qfq",
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
):
    with request.app.state.repo.connection() as conn:
        frame = conn.execute(
            "SELECT symbol, min(date) AS start_date, max(date) AS end_date, count(*) AS bars "
            "FROM daily_bars WHERE data_source=? AND adjust_type=? GROUP BY symbol LIMIT ?",
            [source, adjust, limit],
        ).df()
    return records(frame)
