"""Portable strategy definitions: shared by editor, version store and run snapshots."""

from typing import Literal

from pydantic import Field, model_validator

from app.models.schemas_base import StrictModel

Feature = Literal[
    "constant",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "sma",
    "ema",
    "volume_ma",
    "macd_dif",
    "macd_dea",
    "macd_hist",
    "rsi",
    "atr",
    "boll_upper",
    "boll_mid",
    "boll_lower",
    "kdj_k",
    "kdj_d",
    "kdj_j",
]


class Operand(StrictModel):
    feature: Feature = "close"
    value: float = 0
    period: int = Field(default=20, ge=1, le=500, strict=True)
    slope_period: int = Field(default=0, ge=0, le=250, strict=True)
    offset: int = Field(default=0, ge=0, le=250, strict=True)


class Condition(StrictModel):
    left: Operand
    operator: Literal["gt", "gte", "lt", "lte", "cross_up", "cross_down"] = "gt"
    right: Operand
    consecutive: int = Field(default=1, ge=1, le=250, strict=True)


class RuleGroup(StrictModel):
    match: Literal["all", "any"] = "all"
    conditions: list[Condition] = Field(min_length=1, max_length=20)


class RuleDefinition(StrictModel):
    buy: RuleGroup
    sell: RuleGroup


class StrategyDefinition(StrictModel):
    kind: Literal["rules", "python"]
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=2000)
    rules: RuleDefinition | None = None
    code: str = Field(default="", max_length=50000)
    parameters: dict[str, float | int] = Field(default_factory=dict, max_length=50)

    @model_validator(mode="after")
    def valid_body(self):
        self.name = self.name.strip()
        if not self.name:
            raise ValueError("策略名称不能为空")
        if self.kind == "rules" and (self.rules is None or self.code or self.parameters):
            raise ValueError("规则策略需要买卖条件，不能同时包含 Python 代码或参数")
        if self.kind == "python" and (not self.code.strip() or self.rules is not None):
            raise ValueError("Python 策略需要代码，不能同时包含规则定义")
        return self


class SaveStrategyRequest(StrictModel):
    definition: StrategyDefinition
    parent_id: str | None = None
