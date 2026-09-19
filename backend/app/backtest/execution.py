from typing import Protocol

from app.models.schemas import BacktestConfig


class ExecutionPolicy(Protocol):
    def can_execute(self, bar: dict, side: str) -> tuple[bool, str]: ...


class DailyExecutionPolicy:
    """Extend here for price limits / ST / board-specific constraints."""

    def can_execute(self, bar: dict, side: str) -> tuple[bool, str]:
        if bar["volume"] <= 0:
            return False, "无成交量，视为停牌，订单延后"
        return True, ""


def commission(notional: float, config: BacktestConfig) -> float:
    return round(max(config.minimum_commission, notional * config.commission_rate), 2)


def affordable_shares(cash: float, price: float, config: BacktestConfig) -> int:
    shares = int(cash / price / 100) * 100
    while shares > 0 and shares * price + commission(shares * price, config) > cash:
        shares -= 100
    return shares
