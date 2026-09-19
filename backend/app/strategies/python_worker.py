"""Worker only: execute user code and check its output and sampled historical prefixes."""

import copy
import json
import sys
import traceback
from pathlib import Path

import pandas as pd

from app.services.serialization import records
from app.strategies.contracts import validate_signals


def execute(payload: dict) -> dict:
    data = pd.DataFrame(payload["bars"])
    data["date"] = pd.to_datetime(data.date).dt.date

    def calculate(frame):
        namespace = {"__name__": "user_strategy"}
        exec(compile(payload["code"], "user_strategy.py", "exec"), namespace)  # noqa: S102
        function = namespace.get("generate_signals")
        if not callable(function):
            raise TypeError("generate_signals 必须是可调用函数")
        return validate_signals(function(frame.copy(deep=True), copy.deepcopy(payload["params"])), frame)

    signals = calculate(data)
    # This detects common lookahead mistakes; it is not a proof for arbitrary Python.
    for cut in sorted({len(data) // 2, len(data) - 1}):
        if cut < 2:
            continue
        partial = calculate(data.iloc[:cut])
        try:
            pd.testing.assert_frame_equal(signals.iloc[:cut], partial, check_dtype=False)
        except AssertionError as exc:
            raise ValueError(
                f"历史前缀检查失败（前 {cut} 根）：信号随未来数据改变，或策略含随机/外部状态"
            ) from exc
    return {"signals": records(signals)}


def main():
    output = Path(sys.argv[2])
    try:
        result = execute(json.loads(Path(sys.argv[1]).read_text()))
    except BaseException as exc:  # noqa: BLE001 -- report user SystemExit/errors to parent process
        frames = traceback.extract_tb(exc.__traceback__)
        user_frames = [f for f in frames if f.filename == "user_strategy.py"]
        line = f" 第 {user_frames[-1].lineno} 行" if user_frames else ""
        result = {"error": f"Python{line}：{type(exc).__name__}: {str(exc)[:1500]}"}
    output.write_text(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
