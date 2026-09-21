"""读取工作台已有行情，离线评估候选策略；不向研究数据库写入实验。"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

import pandas as pd
import requests
from app.backtest.engine import BacktestEngine
from app.models.schemas import BacktestConfig
from app.strategies import STRATEGIES
from app.strategies.contracts import validate_signals
from app.strategies.python_runner import run_python_strategy

root = Path(__file__).resolve().parent
output = root.parents[1] / "output" / "swing-000938"
output.mkdir(parents=True, exist_ok=True)
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--api-base", default="http://127.0.0.1:8000/api")
parser.add_argument("--start", default="2021-09-19")
parser.add_argument("--end", default="2026-09-18")
args = parser.parse_args()
response = requests.get(
    args.api_base.rstrip("/") + "/stocks/000938/bars",
    params={
        "start_date": args.start,
        "end_date": args.end,
        "source": "tencent",
        "adjust": "qfq",
    },
    timeout=30,
)
response.raise_for_status()
bars_payload = response.json()
if not bars_payload["bars"]:
    raise SystemExit("本地没有000938的腾讯前复权行情，请先下载或调整日期范围")
(output / "input-bars.json").write_text(
    json.dumps(bars_payload, ensure_ascii=False), encoding="utf-8"
)
code = (root / "strategy.py").read_text()
spec = importlib.util.spec_from_file_location("swing", root / "strategy.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

d = pd.DataFrame(bars_payload["bars"])
d["date"] = pd.to_datetime(d.date).dt.date
config = BacktestConfig()
s = run_python_strategy(d, code, m.DEFAULT_PARAMS)
for cut in [1, 2, 14, 60, 65, 100, 250, 600, len(d) - 1]:
    short = m.generate_signals(d.iloc[:cut], m.DEFAULT_PARAMS)
    pd.testing.assert_frame_equal(short, s.iloc[:cut], check_dtype=False)


def run(frame, kind, params=None, cfg=config):
    if kind == "swing":
        sig = validate_signals(
            m.generate_signals(frame, params or m.DEFAULT_PARAMS), frame
        )
    elif kind == "ma_cross":
        strategy = STRATEGIES[kind]
        p = strategy.validate_params({"fast_ma": 5, "slow_ma": 20})
        sig = strategy.generate_signals(strategy.prepare(frame, p), p)
    else:
        sig = pd.DataFrame(
            {
                "date": frame.date,
                "signal": ["BUY"] + ["HOLD"] * (len(frame) - 1),
                "position_target": 1,
                "reason": "买入并持有基准",
            }
        )
    r = BacktestEngine().run("000938", frame, sig, cfg)
    r["signals"] = sig.to_dict("records")
    return r


results = {k: run(d, k) for k in ["swing", "ma_cross", "hold"]}
# 预先固定两个连续日历分段；各段独立空仓开始，与系统相同在段内预热。
segments = []
for start, end in [("2021-09-22", "2023-12-31"), ("2024-01-01", "2026-09-18")]:
    frame = d[
        (d.date >= pd.Timestamp(start).date()) & (d.date <= pd.Timestamp(end).date())
    ].reset_index(drop=True)
    if frame.empty:
        continue
    segments.append(
        {
            "start": str(frame.date.iloc[0]),
            "end": str(frame.date.iloc[-1]),
            "metrics": {k: run(frame, k)["metrics"] for k in results},
        }
    )
variants = []
for changes in [
    {"max_entry_atr": 1.5},
    {"max_entry_atr": 2.5},
    {"trailing_atr": 2.5},
    {"trailing_atr": 3.5},
]:
    r = run(d, "swing", {**m.DEFAULT_PARAMS, **changes})
    variants.append({"changes": changes, "metrics": r["metrics"]})


# 未来窗口只在此评价脚本出现，不提供给策略函数。
def entry_diagnostics(result):
    dates = {day: i for i, day in enumerate(d.date)}
    records = []
    for fill in result["fills"]:
        if fill["side"] != "BUY":
            continue
        i = dates[fill["date"]]
        entry = fill["price"]
        row = {
            "signal_date": str(fill["signal_date"]),
            "entry_date": str(fill["date"]),
            "price": entry,
            "reason": fill["reason"],
        }
        for n in [5, 10, 20]:
            # 含成交当天共N个交易日，末根收盘；不含卖出费，非策略实际平仓收益。
            frame = d.iloc[i : i + n]
            row[f"complete_{n}"] = len(frame) == n
            if len(frame) == n:
                row[f"return_{n}"] = float(frame.close.iloc[-1] / entry - 1)
                row[f"mae_{n}"] = float(frame.low.min() / entry - 1)
                row[f"mfe_{n}"] = float(frame.high.max() / entry - 1)
        records.append(row)
    summary = {}
    for n in [5, 10, 20]:
        complete = [r for r in records if r[f"complete_{n}"]]
        summary[str(n)] = {
            "count": len(complete),
            "positive": sum(r[f"return_{n}"] > 0 for r in complete),
            "average_return": sum(r[f"return_{n}"] for r in complete) / len(complete)
            if complete
            else None,
            "median_mae": float(pd.Series([r[f"mae_{n}"] for r in complete]).median())
            if complete
            else None,
        }
    return {"entries": records, "summary": summary}


entries = {k: entry_diagnostics(r) for k, r in results.items() if k != "hold"}
report = {
    "symbol": "000938",
    "source": "tencent",
    "adjust": "qfq",
    "start": str(d.date.iloc[0]),
    "end": str(d.date.iloc[-1]),
    "bars": len(d),
    "code_sha256": hashlib.sha256(code.encode()).hexdigest(),
    "config": config.model_dump(),
    "parameters": m.DEFAULT_PARAMS,
    "data_sha256": hashlib.sha256(
        json.dumps(bars_payload, sort_keys=True).encode()
    ).hexdigest(),
    "full": results,
    "segments": segments,
    "variants": variants,
    "entries": entries,
    "cost_stress": run(
        d,
        "swing",
        cfg=config.model_copy(update={"slippage": 0.002, "commission_rate": 0.0006}),
    )["metrics"],
}
(output / "report.json").write_text(
    json.dumps(report, default=str, ensure_ascii=False, indent=2)
)
print(
    json.dumps(
        {
            "metrics": {k: r["metrics"] for k, r in results.items()},
            "entry_summary": {k: r["summary"] for k, r in entries.items()},
        },
        ensure_ascii=False,
        indent=2,
    )
)
