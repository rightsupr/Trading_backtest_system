import json
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from threading import RLock
from uuid import uuid4

import duckdb
import pandas as pd


class Repository:
    """One process owns DuckDB. Each operation opens a connection under a shared lock."""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = RLock()
        with self.connection() as conn:
            conn.execute(Path(__file__).with_name("schema.sql").read_text())

    @contextmanager
    def connection(self):
        with self.lock:
            conn = duckdb.connect(str(self.path))
            try:
                yield conn
            finally:
                conn.close()

    def bars(self, symbol: str, start: date, end: date, adjust: str, source: str) -> pd.DataFrame:
        with self.connection() as conn:
            frame = conn.execute(
                "SELECT * FROM daily_bars WHERE symbol=? AND date BETWEEN ? AND ? "
                "AND adjust_type=? AND data_source=? ORDER BY date",
                [symbol, start, end, adjust, source],
            ).df()
        frame["date"] = pd.to_datetime(frame.date).dt.date
        return frame

    def bounds(self, symbol: str, adjust: str, source: str):
        with self.connection() as conn:
            return conn.execute(
                "SELECT min(date), max(date) FROM daily_bars WHERE symbol=? AND adjust_type=? AND data_source=?",
                [symbol, adjust, source],
            ).fetchone()

    def saved_stocks(self) -> list[dict]:
        """Discover existing caches too; no separate watchlist migration is required."""
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT b.symbol, coalesce(s.name, b.symbol), b.adjust_type, b.data_source, "
                "min(b.date), max(b.date), count(*), max(b.updated_at), "
                "u.checked_at, u.target_date, u.status, u.message "
                "FROM daily_bars b LEFT JOIN stocks s ON s.symbol=b.symbol "
                "LEFT JOIN market_update_status u ON u.symbol=b.symbol "
                "AND u.adjust_type=b.adjust_type AND u.data_source=b.data_source "
                "GROUP BY b.symbol, s.name, b.adjust_type, b.data_source, "
                "u.checked_at, u.target_date, u.status, u.message "
                "ORDER BY b.symbol, b.data_source, b.adjust_type"
            ).fetchall()
        keys = [
            "symbol",
            "name",
            "adjust",
            "source",
            "start_date",
            "end_date",
            "bars",
            "updated_at",
            "checked_at",
            "target_date",
            "status",
            "message",
        ]
        return [
            dict(zip(keys, [str(v) if v is not None and i in (4, 5, 7, 9) else v for i, v in enumerate(row)]))
            for row in rows
        ]

    def auto_update_enabled(self) -> bool:
        with self.connection() as conn:
            return conn.execute("SELECT enabled FROM market_update_settings WHERE id=1").fetchone()[0]

    def save_stock_names(self, names: dict[str, str]):
        with self.connection() as conn:
            for symbol, name in names.items():
                conn.execute("UPDATE stocks SET name=? WHERE symbol=?", [name, symbol])

    def set_auto_update(self, enabled: bool):
        with self.connection() as conn:
            conn.execute("UPDATE market_update_settings SET enabled=? WHERE id=1", [enabled])

    def record_market_update(self, symbol, adjust, source, checked_at, target, status, message):
        with self.connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO market_update_status VALUES (?, ?, ?, ?, ?, ?, ?)",
                [symbol, adjust, source, checked_at, target, status, message],
            )

    def upsert_bars(
        self,
        symbol: str,
        adjust: str,
        source: str,
        frame: pd.DataFrame,
        replace: tuple[date, date] | None = None,
    ) -> int:
        fields = [
            "date",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
            "turnover",
            "pre_close",
            "change",
            "pct_change",
        ]
        rows = frame[fields].copy()
        rows.insert(0, "symbol", symbol)
        rows["adjust_type"], rows["data_source"] = adjust, source
        with self.connection() as conn:
            conn.execute("BEGIN TRANSACTION")
            try:
                if replace:
                    conn.execute(
                        "DELETE FROM daily_bars WHERE symbol=? AND adjust_type=? AND data_source=? "
                        "AND date BETWEEN ? AND ?",
                        [symbol, adjust, source, *replace],
                    )
                conn.register("incoming", rows)
                conn.execute("INSERT OR REPLACE INTO daily_bars SELECT *, current_timestamp FROM incoming")
                conn.execute(
                    "INSERT INTO stocks VALUES (?, ?, current_timestamp) "
                    "ON CONFLICT(symbol) DO UPDATE SET updated_at=excluded.updated_at",
                    [symbol, symbol],
                )
                conn.execute(
                    "DELETE FROM market_update_status WHERE symbol=? AND adjust_type=? AND data_source=?",
                    [symbol, adjust, source],
                )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return len(rows)

    def save_run(self, result: dict):
        req = result["request"]
        with self.connection() as conn:
            conn.execute("BEGIN TRANSACTION")
            try:
                conn.execute(
                    "INSERT INTO strategy_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, current_timestamp, ?)",
                    [
                        result["run_id"],
                        req["symbol"],
                        req["strategy_name"],
                        result["strategy_version"],
                        json.dumps(req["parameters"]),
                        req["start_date"],
                        req["end_date"],
                        req["config"]["initial_cash"],
                        json.dumps(result, allow_nan=False),
                    ],
                )
                if result["signals"]:
                    conn.executemany(
                        "INSERT INTO signals VALUES (?, ?, ?, ?, ?)",
                        [
                            [result["run_id"], s["date"], s["signal"], s["position_target"], s["reason"]]
                            for s in result["signals"]
                        ],
                    )
                if result["trades"]:
                    conn.executemany(
                        "INSERT INTO trades VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        [
                            [
                                t["trade_id"],
                                result["run_id"],
                                req["symbol"],
                                t["entry_date"],
                                t["exit_date"],
                                t["entry_price"],
                                t["exit_price"],
                                t["shares"],
                                t["profit"],
                                json.dumps(t),
                            ]
                            for t in result["trades"]
                        ],
                    )
                if result["equity"]:
                    conn.executemany(
                        "INSERT INTO equity_curve VALUES (?, ?, ?, ?, ?, ?)",
                        [
                            [
                                result["run_id"],
                                e["date"],
                                e["cash"],
                                e["position_value"],
                                e["total_equity"],
                                e["drawdown"],
                            ]
                            for e in result["equity"]
                        ],
                    )
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise

    def get_run(self, run_id: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute("SELECT result_json FROM strategy_runs WHERE run_id=?", [run_id]).fetchone()
        return json.loads(row[0]) if row else None

    def list_runs(self) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT run_id, symbol, strategy_name, created_at FROM strategy_runs "
                "ORDER BY created_at DESC LIMIT 100"
            ).fetchall()
        return [dict(zip(["run_id", "symbol", "strategy_name", "created_at"], map(str, row))) for row in rows]

    def save_definition(self, definition: dict, content_hash: str, parent_id: str | None = None) -> dict:
        identifier = str(uuid4())
        with self.connection() as conn:
            family, revision = identifier, 1
            if parent_id:
                parent = conn.execute(
                    "SELECT family_id FROM strategy_definitions WHERE definition_id=?", [parent_id]
                ).fetchone()
                if parent is None:
                    raise ValueError("原策略版本不存在，请另存为新策略")
                family = parent[0]
                revision = conn.execute(
                    "SELECT max(revision)+1 FROM strategy_definitions WHERE family_id=?", [family]
                ).fetchone()[0]
            conn.execute(
                "INSERT INTO strategy_definitions VALUES (?, ?, ?, ?, ?, ?, ?, current_timestamp)",
                [
                    identifier,
                    family,
                    revision,
                    definition["name"],
                    definition["kind"],
                    json.dumps(definition),
                    content_hash,
                ],
            )
        return self.get_definition(identifier)

    def get_definition(self, identifier: str) -> dict | None:
        with self.connection() as conn:
            row = conn.execute(
                "SELECT definition_id, family_id, revision, definition_json, content_hash, created_at "
                "FROM strategy_definitions WHERE definition_id=?",
                [identifier],
            ).fetchone()
        if row is None:
            return None
        return {
            "definition_id": row[0],
            "family_id": row[1],
            "revision": row[2],
            "definition": json.loads(row[3]),
            "content_hash": row[4],
            "created_at": str(row[5]),
        }

    def list_definitions(self) -> list[dict]:
        with self.connection() as conn:
            rows = conn.execute(
                "SELECT definition_id, family_id, revision, name, kind, created_at "
                "FROM strategy_definitions ORDER BY created_at DESC"
            ).fetchall()
        return [
            {
                "definition_id": r[0],
                "family_id": r[1],
                "revision": r[2],
                "name": r[3],
                "kind": r[4],
                "created_at": str(r[5]),
            }
            for r in rows
        ]
