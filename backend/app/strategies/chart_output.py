"""Optional plotted columns returned by a trusted Python strategy."""

import re

import numpy as np
import pandas as pd

from app.services.serialization import clean


def chart_output(value: pd.DataFrame) -> list[dict]:
    specifications = value.attrs.get("plots")
    if specifications is None:
        specifications = [
            {"column": c, "label": c[5:], "pane": "price"}
            for c in value.columns
            if isinstance(c, str) and c.startswith("plot_")
        ]
    if not isinstance(specifications, list) or len(specifications) > 20:
        raise ValueError("plots 必须是列表，最多支持 20 个指标")
    plots, seen = [], set()
    for spec in specifications:
        if not isinstance(spec, dict):
            raise TypeError("每个 plots 项需要 column、label 和 pane")
        column = spec.get("column")
        if not isinstance(column, str) or column not in value or column in seen:
            raise ValueError("绘图 column 必须存在且不能重复")
        if not value.columns.is_unique:
            raise ValueError("策略返回列名不能重复")
        seen.add(column)
        label = spec.get("label", column)
        pane = spec.get("pane", "price")
        color = spec.get("color", "#8b6cc1")
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= 60:
            raise ValueError("指标名称需要 1 至 60 个字符")
        if not isinstance(pane, str) or not 1 <= len(pane) <= 40:
            raise ValueError("pane 使用 price（主图）或最多 40 字的副图名称")
        if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise ValueError("指标颜色需要六位十六进制值，例如 #d6a148")
        series = value[column]
        if not pd.api.types.is_numeric_dtype(series) and not series.isna().all():
            raise ValueError(f"指标 {column} 必须为数值列，预热期可为空")
        numbers = series.to_numpy(dtype=float, na_value=np.nan)
        if np.isinf(numbers).any():
            raise ValueError(f"指标 {column} 不能含无穷值")
        plots.append(
            {
                "key": f"python:{column}",
                "label": label.strip(),
                "pane": pane,
                "color": color,
                "values": clean(numbers.tolist()),
            }
        )
    return plots
