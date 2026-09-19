import pandas as pd


def validate_signals(value, data: pd.DataFrame) -> pd.DataFrame:
    columns = ["date", "signal", "position_target", "reason"]
    if not isinstance(value, pd.DataFrame) or not set(columns).issubset(value.columns):
        raise ValueError("generate_signals 必须返回包含 date、signal、position_target、reason 的 DataFrame")
    result = value[columns].copy().reset_index(drop=True)
    if len(result) != len(data):
        raise ValueError("信号行数必须与输入行情相同，预热期也需返回 NONE")
    result["date"] = pd.to_datetime(result.date, errors="raise").dt.date
    if result.date.tolist() != pd.to_datetime(data.date).dt.date.tolist():
        raise ValueError("信号日期必须与行情逐行一致，不能缺失、重复或重新排序")
    if not result.signal.isin(["BUY", "SELL", "HOLD", "NONE"]).all():
        raise ValueError("signal 仅支持 BUY / SELL / HOLD / NONE")
    if not result.position_target.isin([0, 1]).all():
        raise ValueError("position_target 仅支持 0（空仓）或 1（满仓）")
    if not result.reason.map(lambda x: isinstance(x, str) and 0 < len(x.strip()) <= 2000).all():
        raise ValueError("每一行都需要非空 reason（最多 2000 字）")
    target = 0
    for row in result.itertuples():
        expected = 1 if row.signal == "BUY" else 0 if row.signal == "SELL" else target
        if (
            row.position_target != expected
            or (row.signal == "HOLD" and expected != 1)
            or (row.signal == "NONE" and expected != 0)
        ):
            raise ValueError(f"{row.date}: signal 与 position_target 不一致；持仓用 HOLD，空仓用 NONE")
        target = expected
    return result
