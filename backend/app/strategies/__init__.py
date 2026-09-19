from app.strategies.crossovers import MACDStrategy, MovingAverageStrategy

STRATEGIES = {s.name: s for s in [MovingAverageStrategy(), MACDStrategy()]}


def register_strategy(strategy):
    if strategy.name in STRATEGIES:
        raise ValueError(f"策略名称重复：{strategy.name}")
    STRATEGIES[strategy.name] = strategy
