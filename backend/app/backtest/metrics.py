import math

import numpy as np


def statistics(equity: list[dict], trades: list[dict], initial_cash: float) -> dict:
    final = equity[-1]["total_equity"]
    total_return = final / initial_cash - 1
    # 252-session annualization; includes the initial cash baseline.
    exponent = math.log(final / initial_cash) * 252 / len(equity) if final > 0 else -math.inf
    annualized = math.expm1(exponent) if exponent < 700 else None
    returns = [t["net_return"] for t in trades]
    wins = [t["profit"] for t in trades if t["profit"] > 0]
    losses = [t["profit"] for t in trades if t["profit"] < 0]
    max_wins = max_losses = streak_wins = streak_losses = 0
    for trade in trades:
        streak_wins = streak_wins + 1 if trade["profit"] > 0 else 0
        streak_losses = streak_losses + 1 if trade["profit"] < 0 else 0
        max_wins, max_losses = max(max_wins, streak_wins), max(max_losses, streak_losses)
    return {
        "initial_cash": initial_cash,
        "final_equity": final,
        "total_return": total_return,
        "annualized_return": annualized,
        "max_drawdown": min(e["drawdown"] for e in equity),
        "win_rate": len(wins) / len(trades) if trades else 0,
        "profit_loss_ratio": float(np.mean(wins) / abs(np.mean(losses))) if wins and losses else None,
        "number_of_trades": len(trades),
        "average_trade_return": float(np.mean(returns)) if returns else 0,
        "average_holding_days": float(np.mean([t["holding_days"] for t in trades])) if trades else 0,
        "best_trade": max(returns) if returns else None,
        "worst_trade": min(returns) if returns else None,
        "maximum_consecutive_wins": max_wins,
        "maximum_consecutive_losses": max_losses,
    }
