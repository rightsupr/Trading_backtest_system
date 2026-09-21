CREATE TABLE IF NOT EXISTS stocks (
    symbol VARCHAR PRIMARY KEY, name VARCHAR, updated_at TIMESTAMP DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS daily_bars (
    symbol VARCHAR NOT NULL, date DATE NOT NULL,
    open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE, volume DOUBLE,
    amount DOUBLE, turnover DOUBLE, pre_close DOUBLE, change DOUBLE, pct_change DOUBLE,
    adjust_type VARCHAR NOT NULL, data_source VARCHAR NOT NULL,
    updated_at TIMESTAMP DEFAULT current_timestamp,
    PRIMARY KEY (symbol, date, adjust_type, data_source)
);
CREATE TABLE IF NOT EXISTS strategy_runs (
    run_id VARCHAR PRIMARY KEY, symbol VARCHAR, strategy_name VARCHAR, strategy_version VARCHAR,
    parameters_json JSON, start_date DATE, end_date DATE, initial_cash DOUBLE,
    created_at TIMESTAMP DEFAULT current_timestamp, result_json JSON
);
CREATE TABLE IF NOT EXISTS signals (
    run_id VARCHAR, date DATE, signal VARCHAR, position_target DOUBLE, reason VARCHAR,
    PRIMARY KEY(run_id, date)
);
CREATE TABLE IF NOT EXISTS trades (
    trade_id VARCHAR PRIMARY KEY, run_id VARCHAR, symbol VARCHAR,
    entry_date DATE, exit_date DATE, entry_price DOUBLE, exit_price DOUBLE,
    shares INTEGER, profit DOUBLE, payload JSON
);
CREATE TABLE IF NOT EXISTS equity_curve (
    run_id VARCHAR, date DATE, cash DOUBLE, position_value DOUBLE, total_equity DOUBLE, drawdown DOUBLE,
    PRIMARY KEY(run_id, date)
);
CREATE TABLE IF NOT EXISTS strategy_definitions (
    definition_id VARCHAR PRIMARY KEY, family_id VARCHAR NOT NULL, revision INTEGER NOT NULL,
    name VARCHAR NOT NULL, kind VARCHAR NOT NULL, definition_json JSON NOT NULL,
    content_hash VARCHAR NOT NULL, created_at TIMESTAMP DEFAULT current_timestamp,
    UNIQUE(family_id, revision)
);
CREATE TABLE IF NOT EXISTS experiment_metadata (
    run_id VARCHAR PRIMARY KEY, is_favorite BOOLEAN NOT NULL DEFAULT false
);
ALTER TABLE strategy_definitions ADD COLUMN IF NOT EXISTS deleted BOOLEAN DEFAULT false;
CREATE TABLE IF NOT EXISTS market_update_settings (
    id INTEGER PRIMARY KEY, enabled BOOLEAN NOT NULL
);
INSERT INTO market_update_settings SELECT 1, true
WHERE NOT EXISTS (SELECT 1 FROM market_update_settings WHERE id=1);
CREATE TABLE IF NOT EXISTS market_update_status (
    symbol VARCHAR, adjust_type VARCHAR, data_source VARCHAR,
    checked_at VARCHAR NOT NULL, target_date DATE NOT NULL,
    status VARCHAR NOT NULL, message VARCHAR NOT NULL,
    PRIMARY KEY (symbol, adjust_type, data_source)
);
