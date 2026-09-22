"""预定邻近参数及费用检查，不据此重新选择参数。先运行两个标的的evaluate.py。"""

import json
from pathlib import Path

import pandas as pd
from app.models.schemas import BacktestConfig
from evaluate import run_case

output = Path(__file__).resolve().parents[2] / "output/exit-research-000938"
results = {}
for symbol in ["000938", "002396"]:
    data = pd.DataFrame(
        json.loads((output / f"{symbol}-bars.json").read_text())["bars"]
    )
    data.date = pd.to_datetime(data.date).dt.date
    neighbors = []
    for value in [1.25, 1.75]:
        result = run_case(data, symbol, "locked_guard", {"profit_trailing_atr": value})
        neighbors.append({"profit_trailing_atr": value, "metrics": result["metrics"]})
    stress = {
        kind: run_case(
            data,
            symbol,
            kind,
            config=BacktestConfig(commission_rate=0.0006, slippage=0.002),
        )["metrics"]
        for kind in ["baseline", "locked_guard"]
    }
    results[symbol] = {"neighbors": neighbors, "cost_stress": stress}
(output / "robustness.json").write_text(
    json.dumps(results, ensure_ascii=False, indent=2)
)
print(output / "robustness.json")
