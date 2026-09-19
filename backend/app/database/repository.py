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
                    "INSERT OR REPLACE INTO stocks VALUES (?, ?, current_timestamp)", [symbol, symbol]
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
