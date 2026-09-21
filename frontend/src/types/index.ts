import type { StrategyDefinition } from "./strategy";
export interface Query {
  symbol: string;
  start_date: string;
  end_date: string;
  adjust: "raw" | "qfq" | "hfq";
  source: "eastmoney" | "tencent" | "sample";
}
export interface SavedStock {
  symbol: string;
  name: string;
  source: Query["source"];
  adjust: Query["adjust"];
  start_date: string;
  end_date: string;
  bars: number;
  updated_at: string;
  checked_at: string | null;
  status: "success" | "waiting" | "error" | "refresh_required" | null;
  message: string | null;
}
export interface WatchlistData {
  stocks: SavedStock[];
  enabled: boolean;
  running: boolean;
  schedule: string;
  target_date: string;
}
export interface Config {
  initial_cash: number;
  commission_rate: number;
  minimum_commission: number;
  stamp_tax_rate: number;
  slippage: number;
}
export interface Bar {
  [key: string]: string | number | null | undefined;
  date: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  pre_close?: number | null;
  pct_change?: number | null;
  sma_5: number | null;
  sma_20: number | null;
  strategy_fast?: number | null;
  strategy_slow?: number | null;
  macd_dif: number | null;
  macd_dea: number | null;
  macd_hist: number | null;
}
export interface Trade {
  trade_id: string;
  symbol: string;
  entry_date: string;
  exit_date: string;
  entry_signal_date: string;
  exit_signal_date: string;
  entry_price: number;
  exit_price: number;
  entry_reason: string;
  exit_reason: string;
  shares: number;
  holding_days: number;
  holding_bars: number;
  gross_return: number;
  net_return: number;
  profit: number;
  commission: number;
  tax: number;
  MFE: number;
  MAE: number;
  max_profit_during_trade: number;
  max_drawdown_during_trade: number;
}
export interface Fill {
  date: string;
  signal_date: string;
  side: "BUY" | "SELL";
  price: number;
  shares: number;
  reason: string;
  trade_id: string;
}
export interface Equity {
  date: string;
  cash: number;
  position_value: number;
  total_equity: number;
  drawdown: number;
}
export interface Run {
  chart_series?: ChartSeries[];
  run_id: string;
  created_at: string;
  strategy_version: string;
  data_hash: string;
  request: Query & {
    strategy_name: string;
    parameters: Record<string, number>;
    config: Config;
    custom_strategy?: StrategyDefinition | null;
  };
  bars: Bar[];
  trades: Trade[];
  fills: Fill[];
  equity: Equity[];
  metrics: Record<string, number | null>;
  open_position: {
    trade_id: string;
    entry_date: string;
    last_date: string;
    shares: number;
    entry_price: number;
    unrealized_profit: number;
  } | null;
  rejected_orders: { date: string; side: string; reason: string }[];
  warnings: string[];
}
export interface ChartSeries {
  key: string;
  label: string;
  pane: string;
  color: string;
  values: (number | null)[];
}
export interface Strategy {
  name: string;
  label: string;
  version: string;
  parameters: {
    properties: Record<
      string,
      { default: number; minimum?: number; maximum?: number }
    >;
  };
}
export interface RunSummary {
  run_id: string;
  symbol: string;
  strategy_name: string;
  created_at: string;
}
