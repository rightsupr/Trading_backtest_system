"""Local trusted Python in a disposable subprocess, NOT a security sandbox."""

import ast
import json
import os
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

import pandas as pd

from app.services.serialization import records
from app.strategies.contracts import validate_signals


def check_python_syntax(code: str):
    try:
        tree = ast.parse(code, filename="user_strategy.py")
        compile(tree, "user_strategy.py", "exec")
    except SyntaxError as exc:
        raise ValueError(f"Python 第 {exc.lineno} 行语法错误：{exc.msg}") from exc
    if not any(isinstance(node, ast.FunctionDef) and node.name == "generate_signals" for node in tree.body):
        raise ValueError("请定义入口函数 def generate_signals(data, params):")


def run_python_strategy(data: pd.DataFrame, code: str, params: dict, timeout: float = 15) -> pd.DataFrame:
    check_python_syntax(code)
    with tempfile.TemporaryDirectory(prefix="quant-strategy-") as directory:
        root = Path(directory)
        source = root / "input.json"
        output = root / "result.json"
        source.write_text(
            json.dumps({"code": code, "params": params, "bars": records(data)}, allow_nan=False)
        )
        # No shell interpolation; the project package is already installed in this venv.
        process = subprocess.Popen(
            [sys.executable, "-m", "app.strategies.python_worker", str(source), str(output)],
            cwd=root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.wait()
            raise ValueError(f"Python 策略执行超过 {timeout:g} 秒，已终止；请检查死循环或减少计算量") from exc
        if not output.exists() or output.stat().st_size > 20_000_000:
            raise ValueError("Python 策略进程异常退出或输出过大，请检查代码")
        try:
            result = json.loads(output.read_text())
        except (ValueError, OSError) as exc:
            raise ValueError("Python 策略返回了无法读取的结果") from exc
        if "error" in result:
            raise ValueError(result["error"])
        return validate_signals(pd.DataFrame(result["signals"]), data)
