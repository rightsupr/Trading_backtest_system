"""Read trusted local strategies from the project's strategy directory."""

import ast
from pathlib import Path

from app.config import ROOT
from app.models.strategy import StrategyDefinition
from app.strategies.python_runner import check_python_syntax

STRATEGY_DIR = ROOT / "strategy"


def list_strategy_files() -> list[dict[str, str]]:
    if not STRATEGY_DIR.is_dir():
        return []
    return [
        {"filename": path.name, "name": path.stem}
        for path in sorted(STRATEGY_DIR.glob("*.py"), key=lambda path: path.name.lower())
        if path.is_file() and not path.is_symlink() and not path.name.startswith("_")
    ]


def load_strategy_file(filename: str) -> StrategyDefinition:
    # Only a direct .py child is accepted; resolved paths must stay inside the folder.
    if (
        not filename
        or filename != Path(filename).name
        or filename.startswith("_")
        or not filename.endswith(".py")
    ):
        raise ValueError("只能选择 strategy 文件夹中的 Python 策略文件")
    path = STRATEGY_DIR / filename
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"策略文件不存在：{filename}")
    try:
        if path.resolve().parent != STRATEGY_DIR.resolve():
            raise ValueError("只能选择 strategy 文件夹中的 Python 策略文件")
        if path.stat().st_size > 50_000:
            raise ValueError("策略文件超过 50 KB，请缩小代码后重试")
        code = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"无法读取策略文件：{filename}") from exc
    check_python_syntax(code)
    description = ast.get_docstring(ast.parse(code)) or ""
    description = description.splitlines()[0][:2000] if description else ""
    return StrategyDefinition(
        kind="python", name=path.stem[:80], description=description, code=code, parameters={}
    )
