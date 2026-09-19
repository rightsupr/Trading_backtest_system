import hashlib
import json

from app.models.strategy import StrategyDefinition
from app.strategies.contracts import validate_signals
from app.strategies.python_runner import check_python_syntax, run_python_strategy
from app.strategies.rules import generate_rule_signals


def definition_hash(definition: StrategyDefinition) -> str:
    return hashlib.sha256(
        json.dumps(definition.model_dump(), sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def validate_definition(definition: StrategyDefinition):
    if definition.kind == "python":
        check_python_syntax(definition.code)


def custom_signals(data, definition: StrategyDefinition):
    if definition.kind == "python":
        return run_python_strategy(data, definition.code, definition.parameters)
    return validate_signals(generate_rule_signals(data, definition.rules), data)
