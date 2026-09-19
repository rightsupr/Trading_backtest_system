from fastapi import APIRouter, HTTPException, Request

from app.models.schemas import BacktestRequest
from app.models.strategy import SaveStrategyRequest
from app.services.custom_strategies import definition_hash, validate_definition
from app.services.research import prepare_research
from app.services.serialization import records
from app.strategies.templates import PYTHON_EXAMPLES

router = APIRouter(prefix="/api/strategy-editor", tags=["strategy-editor"])


@router.get("/examples")
def examples():
    return PYTHON_EXAMPLES


@router.get("/definitions")
def definitions(request: Request):
    return request.app.state.repo.list_definitions()


@router.post("/definitions")
def save_definition(body: SaveStrategyRequest, request: Request):
    validate_definition(body.definition)
    return request.app.state.repo.save_definition(
        body.definition.model_dump(), definition_hash(body.definition), body.parent_id
    )


@router.get("/definitions/{definition_id}")
def get_definition(definition_id: str, request: Request):
    result = request.app.state.repo.get_definition(definition_id)
    if result is None:
        raise HTTPException(404, "未找到策略版本")
    return result


@router.post("/validate")
def validate_strategy(body: BacktestRequest, request: Request):
    if body.custom_strategy is None:
        raise ValueError("请选择规则或 Python 策略后再校验")
    _, signals, _, version, _ = prepare_research(request.app.state.repo, body)
    return {
        "valid": True,
        "version": version,
        "rows": len(signals),
        "signal_counts": {k: int(v) for k, v in signals.signal.value_counts().items()},
        "examples": records(signals[signals.signal.isin(["BUY", "SELL"])].head(5)),
        "message": "校验通过。信号格式正确"
        + (
            "，两处历史前缀抽查通过（不等于无未来函数的完整证明）"
            if body.custom_strategy.kind == "python"
            else "，规则仅使用当日及历史数据"
        ),
    }
