import hashlib
import json
import logging
from datetime import UTC, datetime
from uuid import uuid4

from app.backtest.engine import BacktestEngine
from app.indicators.technical import chart_indicators
from app.services.custom_strategies import custom_signals, definition_hash
from app.services.serialization import clean, records
from app.strategies import STRATEGIES

logger = logging.getLogger(__name__)


def prepare_research(repository, request):
    if request.custom_strategy is None and request.strategy_name not in STRATEGIES:
        raise ValueError(f"未知策略：{request.strategy_name}")
    bars = repository.bars(
        request.symbol, request.start_date, request.end_date, request.adjust, request.source
    )
    if bars.empty:
        raise ValueError("本地数据库在此范围内没有行情，请先下载历史数据")
    # Indicators warm up inside the selected range; no position inherited before the range.
    prepared = chart_indicators(bars)
    if request.custom_strategy:
        definition = request.custom_strategy
        params = definition.parameters
        signals = custom_signals(prepared, definition)
        version = definition_hash(definition)
        name = definition.name
    else:
        strategy = STRATEGIES[request.strategy_name]
        params = strategy.validate_params(request.parameters)
        prepared = strategy.prepare(prepared, params)
        signals = strategy.generate_signals(prepared, params)
        version, name = strategy.version, strategy.name
    return prepared, signals, params, version, name


def run_research(repository, request):
    logger.info("Backtest started %s %s", request.symbol, request.strategy_name)
    prepared, signals, params, version, name = prepare_research(repository, request)
    result = BacktestEngine().run(request.symbol, prepared, signals, request.config)
    payload = request.model_dump(mode="json")
    payload["parameters"] = params
    payload["strategy_name"] = name
    snapshot = records(prepared)
    result.update(
        {
            "run_id": str(uuid4()),
            "request": payload,
            "strategy_version": version,
            "created_at": datetime.now(UTC).isoformat(),
            "bars": snapshot,
            "signals": records(signals),
            "data_hash": hashlib.sha256(json.dumps(snapshot).encode()).hexdigest(),
            "warnings": [
                "复权价格用于研究撮合，未独立核算分红送转与历史印花税变化。",
                "不模拟涨跌停封单和市场冲击；停牌订单延后，期末持仓按收盘计价。",
            ],
        }
    )
    result = clean(result)
    repository.save_run(result)
    logger.info("Backtest completed %s: %s trades", result["run_id"], len(result["trades"]))
    return result
