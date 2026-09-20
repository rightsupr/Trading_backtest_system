"""History metadata is separate from immutable backtest snapshots."""


class Experiments:
    def __init__(self, repo):
        self.repo = repo

    def list(self, page=1, page_size=20, favorites=False):
        where = "WHERE coalesce(m.is_favorite, false)" if favorites else ""
        join = "FROM strategy_runs r LEFT JOIN experiment_metadata m USING (run_id)"
        with self.repo.lock:
            with self.repo.connection() as conn:
                total = conn.execute(f"SELECT count(*) {join} {where}").fetchone()[0]
                page = min(page, max(1, (total + page_size - 1) // page_size))
                rows = conn.execute(
                    "SELECT r.run_id, symbol, strategy_name, "
                    "coalesce(json_extract_string(result_json, '$.request.custom_strategy.name'), strategy_name), "
                    "created_at, start_date, end_date, coalesce(m.is_favorite, false), "
                    "octet_length(encode(result_json::VARCHAR)) "
                    f"{join} {where} ORDER BY created_at DESC, r.run_id DESC LIMIT ? OFFSET ?",
                    [page_size, (page - 1) * page_size],
                ).fetchall()
                count, favorite_count, snapshot_bytes = conn.execute(
                    "SELECT count(*), count(*) FILTER (WHERE m.is_favorite), "
                    f"coalesce(sum(octet_length(encode(result_json::VARCHAR))), 0) {join}"
                ).fetchone()
                bar_count = conn.execute("SELECT count(*) FROM daily_bars").fetchone()[0]
            # Read physical sizes after closing the connection/checkpoint; JSON sizes are logical only.
            db_bytes = self.repo.path.stat().st_size
            wal = self.repo.path.with_name(self.repo.path.name + ".wal")
            wal_bytes = wal.stat().st_size if wal.exists() else 0
        keys = [
            "run_id",
            "symbol",
            "strategy_name",
            "label",
            "created_at",
            "start_date",
            "end_date",
            "is_favorite",
            "snapshot_bytes",
        ]
        return {
            "items": [dict(zip(keys, [*r[:4], *map(str, r[4:7]), *r[7:]])) for r in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
            "storage": {
                "database_bytes": db_bytes,
                "wal_bytes": wal_bytes,
                "total_bytes": db_bytes + wal_bytes,
                "snapshot_bytes": snapshot_bytes,
                "run_count": count,
                "favorite_count": favorite_count,
                "bar_count": bar_count,
            },
        }

    def favorite(self, run_id, value):
        with self.repo.connection() as conn:
            if not conn.execute("SELECT 1 FROM strategy_runs WHERE run_id=?", [run_id]).fetchone():
                return None
            conn.execute("INSERT OR REPLACE INTO experiment_metadata VALUES (?, ?)", [run_id, value])
        return {"run_id": run_id, "is_favorite": value}

    def delete(self, run_ids):
        ids = list(dict.fromkeys(run_ids))
        with self.repo.connection() as conn:
            conn.execute("BEGIN TRANSACTION")
            try:
                rows = conn.execute(
                    "SELECT r.run_id, coalesce(m.is_favorite, false) FROM strategy_runs r "
                    "LEFT JOIN experiment_metadata m USING (run_id) WHERE r.run_id IN "
                    "(SELECT unnest(?))",
                    [ids],
                ).fetchall()
                existing = dict(rows)
                deleted = [i for i in ids if i in existing and not existing[i]]
                if deleted:
                    for table in (
                        "signals",
                        "trades",
                        "equity_curve",
                        "experiment_metadata",
                        "strategy_runs",
                    ):
                        conn.execute(f"DELETE FROM {table} WHERE run_id IN (SELECT unnest(?))", [deleted])
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return {
            "deleted_ids": deleted,
            "protected_ids": [i for i in ids if existing.get(i)],
            "missing_ids": [i for i in ids if i not in existing],
        }
