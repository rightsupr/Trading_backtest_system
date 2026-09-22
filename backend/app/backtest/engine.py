from uuid import uuid4

import pandas as pd

from app.backtest.execution import DailyExecutionPolicy, ExecutionPolicy, affordable_shares, commission
from app.backtest.metrics import statistics
from app.models.schemas import BacktestConfig


class BacktestEngine:
    def __init__(self, policy: ExecutionPolicy | None = None):
        self.policy = policy or DailyExecutionPolicy()

    def run(self, symbol: str, bars: pd.DataFrame, signals: pd.DataFrame, config: BacktestConfig) -> dict:
        if bars.empty:
            raise ValueError("所选时间范围没有行情，请先下载数据")
        bars, signals = bars.reset_index(drop=True), signals.reset_index(drop=True)
        if bars.date.tolist() != signals.date.tolist():
            raise ValueError("信号日期必须与行情一一对应")
        if bars.date.duplicated().any() or not bars.date.is_monotonic_increasing:
            raise ValueError("行情必须按日期递增且不能重复")
        if not signals.position_target.isin([0, 1]).all():
            raise ValueError("第一版仅支持 0/1 目标仓位")
        cash, shares, peak = config.initial_cash, 0, config.initial_cash
        position = None
        pending = None
        trades, equity, fills, rejected = [], [], [], []
        same_close = config.execution_timing == "execute_same_close"
        price_field = "close" if same_close else "open"
        for i, bar in enumerate(bars.to_dict("records")):
            # A position carried into today experiences the full session before a close exit.
            if same_close and position:
                self._excursion(position, bar["high"], bar["low"], bar["close"])
            signal_index = i if same_close else i - 1
            if signal_index >= 0:
                current_signal = signals.iloc[signal_index]
                if current_signal.signal in ("BUY", "SELL"):
                    pending = current_signal.to_dict()
            if pending:
                side = pending["signal"]
                actionable = (side == "BUY" and shares == 0) or (side == "SELL" and shares > 0)
                if not actionable:
                    pending = None
                else:
                    allowed, explanation = self.policy.can_execute(bar, side)
                    if not allowed:
                        rejected.append({"date": bar["date"], "side": side, "reason": explanation})
                    elif side == "BUY":
                        price = bar[price_field] * (1 + config.slippage)
                        quantity = affordable_shares(cash, price, config)
                        if quantity == 0:
                            rejected.append(
                                {"date": bar["date"], "side": side, "reason": "资金不足以买入一手及支付费用"}
                            )
                            pending = None
                        else:
                            fee = commission(quantity * price, config)
                            cash -= quantity * price + fee
                            shares = quantity
                            position = {
                                "trade_id": str(uuid4()),
                                "symbol": symbol,
                                "entry_date": bar["date"],
                                "entry_signal_date": pending["date"],
                                "entry_price": price,
                                "entry_reason": pending["reason"],
                                "shares": shares,
                                "entry_commission": fee,
                                "entry_index": i,
                                "high_water": price,
                                "low_water": price,
                                "close_peak": price,
                                "max_drawdown": 0.0,
                            }
                            fills.append(self._fill(bar, pending, price, quantity, position["trade_id"]))
                            pending = None
                    else:
                        price = bar[price_field] * (1 - config.slippage)
                        fee = commission(shares * price, config)
                        tax = round(shares * price * config.stamp_tax_rate, 2)
                        cash += shares * price - fee - tax
                        self._excursion(position, price, price, price)
                        trade = self._close_trade(position, bar, pending, price, fee, tax, i)
                        trades.append(trade)
                        fills.append(self._fill(bar, pending, price, shares, position["trade_id"]))
                        position, shares, pending = None, 0, None
            if position:
                if not same_close:
                    self._excursion(position, bar["high"], bar["low"], bar["close"])
                elif position["entry_index"] == i:
                    # Do not attribute intraday moves before a close entry to this trade.
                    self._excursion(position, bar["close"], bar["close"], bar["close"])
            total = cash + shares * bar["close"]
            peak = max(peak, total)
            equity.append(
                {
                    "date": bar["date"],
                    "cash": cash,
                    "position_value": shares * bar["close"],
                    "total_equity": total,
                    "drawdown": total / peak - 1,
                }
            )
        open_position = None
        if position:
            cost = position["entry_price"] * shares + position["entry_commission"]
            open_position = {
                k: v
                for k, v in position.items()
                if k not in {"entry_index", "high_water", "low_water", "close_peak", "max_drawdown"}
            }
            open_position.update(
                {
                    "last_date": bars.iloc[-1].date,
                    "last_price": float(bars.iloc[-1].close),
                    "unrealized_profit": shares * bars.iloc[-1].close - cost,
                }
            )
        return {
            "trades": trades,
            "equity": equity,
            "fills": fills,
            "rejected_orders": rejected,
            "open_position": open_position,
            "metrics": statistics(equity, trades, config.initial_cash),
        }

    @staticmethod
    def _fill(bar, signal, price, shares, trade_id):
        return {
            "date": bar["date"],
            "signal_date": signal["date"],
            "side": signal["signal"],
            "price": price,
            "shares": shares,
            "reason": signal["reason"],
            "trade_id": trade_id,
        }

    @staticmethod
    def _excursion(position, high, low, close):
        position["high_water"] = max(position["high_water"], high)
        position["low_water"] = min(position["low_water"], low)
        position["close_peak"] = max(position["close_peak"], close)
        position["max_drawdown"] = min(position["max_drawdown"], close / position["close_peak"] - 1)

    @staticmethod
    def _close_trade(position, bar, signal, price, fee, tax, index):
        entry = position["entry_price"]
        cost = entry * position["shares"] + position["entry_commission"]
        profit = price * position["shares"] - fee - tax - cost
        mfe, mae = position["high_water"] / entry - 1, position["low_water"] / entry - 1
        return {
            **{
                k: position[k]
                for k in [
                    "trade_id",
                    "symbol",
                    "entry_date",
                    "entry_signal_date",
                    "entry_price",
                    "entry_reason",
                    "shares",
                ]
            },
            "exit_date": bar["date"],
            "exit_signal_date": signal["date"],
            "exit_price": price,
            "exit_reason": signal["reason"],
            "holding_days": (bar["date"] - position["entry_date"]).days,
            "holding_bars": index - position["entry_index"],
            "gross_return": price / entry - 1,
            "net_return": profit / cost,
            "profit": profit,
            "commission": position["entry_commission"] + fee,
            "tax": tax,
            "max_profit_during_trade": mfe,
            "max_drawdown_during_trade": position["max_drawdown"],
            "MAE": mae,
            "MFE": mfe,
        }
