"""少量预定卖出候选：固定买点诊断 + 完整资金回测；只读现有行情。"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from app.backtest.engine import BacktestEngine
from app.models.schemas import BacktestConfig
from app.strategies.contracts import validate_signals
from candidates import NAMES, candidate_source, load_candidate

KINDS = list(NAMES)
ROOT = Path(__file__).resolve().parents[2]


def price_diagnostics(data, trade):
    dates = {day: i for i, day in enumerate(data.date)}
    start, end = dates[trade["entry_date"]], dates[trade["exit_date"]]
    # 开盘已卖出的当天，高低收都不计入持有期峰值。
    held = data.iloc[start:end]
    peak = float(held.close.max())
    peak_index = held.index[held.close == peak][-1]
    after = data.iloc[end : end + 10]
    return {
        "peak_close": peak,
        "peak_date": str(data.iloc[peak_index].date),
        "peak_gain": peak / trade["entry_price"] - 1,
        "giveback": 1 - trade["exit_price"] / peak,
        "peak_to_exit_bars": int(end - peak_index),
        "after_10_complete": len(after) == 10,
        "after_10_return": float(after.close.iloc[-1] / trade["exit_price"] - 1)
        if len(after) == 10
        else None,
        "after_10_max_return": float(after.close.max() / trade["exit_price"] - 1)
        if len(after) == 10
        else None,
    }


def summary(rows):
    closed = [r for r in rows if r.get("trade")]
    # 仅对曾有正的收盘浮盈的交易衡量盈利回吐，并展示样本数。
    positive = [r for r in closed if r["diagnostics"]["peak_gain"] > 0]
    forward = [r for r in closed if r["diagnostics"]["after_10_complete"]]
    return {
        "closed_count": len(closed),
        "open_count": len(rows) - len(closed),
        "positive_peak_count": len(positive),
        "mean_net_return": float(np.mean([r["trade"]["net_return"] for r in closed]))
        if closed
        else None,
        "median_giveback": float(
            np.median([r["diagnostics"]["giveback"] for r in positive])
        )
        if positive
        else None,
        "median_lag": float(
            np.median([r["diagnostics"]["peak_to_exit_bars"] for r in positive])
        )
        if positive
        else None,
        "forward_complete_count": len(forward),
        "after_exit_10_gain_over_5pct": sum(
            r["diagnostics"]["after_10_max_return"] > 0.05 for r in forward
        ),
    }


def run_case(data, symbol, kind, overrides=None, forced_index=None, config=None):
    function, defaults = load_candidate(kind, fixed_entry=forced_index is not None)
    params = {**defaults, **(overrides or {})}
    sig = (
        function(data, params, forced_index)
        if forced_index is not None
        else function(data, params)
    )
    sig = validate_signals(sig, data)
    result = BacktestEngine().run(symbol, data, sig, config or BacktestConfig())
    result["signals"] = sig.to_dict("records")
    result["diagnostics"] = [
        {"trade": t, "diagnostics": price_diagnostics(data, t)}
        for t in result["trades"]
    ]
    result["exit_summary"] = summary(result["diagnostics"])
    return result


def evaluate(data, symbol):
    full = {k: run_case(data, symbol, k) for k in KINDS}
    dates = {d: i for i, d in enumerate(data.date)}
    entries = [f for f in full["baseline"]["fills"] if f["side"] == "BUY"]
    paired = {k: [] for k in KINDS}
    for fill in entries:
        index = dates[fill["signal_date"]]
        for kind in KINDS:
            r = run_case(data, symbol, kind, forced_index=index)
            buy = next(f for f in r["fills"] if f["side"] == "BUY")
            assert buy["price"] == fill["price"] and buy["date"] == fill["date"]
            trade = r["trades"][0] if r["trades"] else None
            paired[kind].append(
                {
                    "entry_signal_date": str(fill["signal_date"]),
                    "entry_date": str(fill["date"]),
                    "trade": trade,
                    "diagnostics": price_diagnostics(data, trade) if trade else None,
                }
            )
    paired_summary = {}
    for kind, rows in paired.items():
        pairs = [
            (b, a)
            for b, a in zip(paired["baseline"], rows)
            if b["trade"] and a["trade"]
        ]
        diff = [a["trade"]["net_return"] - b["trade"]["net_return"] for b, a in pairs]
        exits_earlier = [
            a["trade"]["exit_date"] < b["trade"]["exit_date"] for b, a in pairs
        ]
        paired_summary[kind] = {
            **summary(rows),
            "paired_count": len(pairs),
            "mean_net_change": float(np.mean(diff)) if diff else None,
            "improved": sum(v > 1e-9 for v in diff),
            "worsened": sum(v < -1e-9 for v in diff),
            "equal": sum(abs(v) <= 1e-9 for v in diff),
            "earlier_count": sum(exits_earlier),
        }
    segments = []
    for start, end in [
        ("2021-01-01", "2023-12-31"),
        ("2024-01-01", "2025-12-31"),
        ("2026-01-01", "2026-12-31"),
    ]:
        frame = data[
            (data.date >= pd.Timestamp(start).date())
            & (data.date <= pd.Timestamp(end).date())
        ].reset_index(drop=True)
        if len(frame) < 30:
            continue
        segments.append(
            {
                "start": str(frame.date.iloc[0]),
                "end": str(frame.date.iloc[-1]),
                "cases": {
                    k: {key: r[key] for key in ["metrics", "exit_summary"]}
                    for k in KINDS
                    for r in [run_case(frame, symbol, k)]
                },
            }
        )
    return {
        "symbol": symbol,
        "start": str(data.date.iloc[0]),
        "end": str(data.date.iloc[-1]),
        "bars": len(data),
        "full": full,
        "fixed_entries": paired,
        "fixed_summary": paired_summary,
        "segments": segments,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbol", default="000938", choices=["000938", "002396"])
    parser.add_argument("--api-base", default="http://127.0.0.1:8000/api")
    args = parser.parse_args()
    directory = ROOT / "output" / "exit-research-000938"
    directory.mkdir(parents=True, exist_ok=True)
    response = requests.get(
        args.api_base.rstrip("/") + f"/stocks/{args.symbol}/bars",
        params={
            "start_date": "2021-09-19",
            "end_date": "2026-09-21",
            "source": "tencent",
            "adjust": "qfq",
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if not payload["bars"]:
        raise SystemExit("没有本地行情，请先下载对应标的腾讯前复权数据")
    (directory / f"{args.symbol}-bars.json").write_text(
        json.dumps(payload, ensure_ascii=False)
    )
    data = pd.DataFrame(payload["bars"])
    data["date"] = pd.to_datetime(data.date).dt.date
    report = evaluate(data, args.symbol)
    report.update(
        {
            "names": NAMES,
            "data_sha256": hashlib.sha256(
                json.dumps(payload, sort_keys=True).encode()
            ).hexdigest(),
            "source_sha256": {
                k: hashlib.sha256(candidate_source(k).encode()).hexdigest()
                for k in KINDS
            },
            "config": BacktestConfig().model_dump(),
        }
    )
    (directory / f"{args.symbol}-report.json").write_text(
        json.dumps(report, default=str, ensure_ascii=False, indent=2)
    )
    print(
        json.dumps(
            {
                "fixed_summary": report["fixed_summary"],
                "full": {k: v["metrics"] for k, v in report["full"].items()},
                "segments": [
                    {
                        **s,
                        "cases": {
                            k: v["metrics"]["total_return"]
                            for k, v in s["cases"].items()
                        },
                    }
                    for s in report["segments"]
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
