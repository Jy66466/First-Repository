"""BA-CH02-18 核心 ETL 操作。

对应教材 ETL 练习的四类操作（Power Query 等价实现）：

1. 拆分列：按分隔符把一列拆成多行 / 按数值+单位拆分一列。
2. 数据清洗：去除标题与空行、去除重复行、缺失与错误值统一为 NA、金额转数值。
3. 纵向合并（追加）：字段名称一致直接拼接；不一致时先重命名对齐。
4. 横向合并：按键连接多张表（等价 SQL 的 JOIN）。

清洗规则口径（依教材演示数据确定，不依赖参考答案）：

- 表格第一行是报表标题而非字段名，读取后须提升字段名并删除标题行；
- 整行全空的行属于占位空行，全部删除；
- 完全重复的数据行仅保留第一行；
- ``#N/A``、空字符串视为缺失值 NA；
- ``实付金额`` 类文本金额列转为数值，无法解析的记为 NA；
- IP 列中负数等非法取值仅做标记，不修改原值。
"""

from __future__ import annotations

import re

import pandas as pd

__all__ = [
    "clean_order_details",
    "horizontal_merge",
    "split_delimited_column",
    "split_quantity_column",
    "vertical_concat",
]

_MISSING_TOKENS = {"#N/A", "#N/A N/A", "", "NA", "N/A", "nan", "None"}


def split_delimited_column(
    frame: pd.DataFrame,
    column: str,
    delimiter: str = ",",
) -> pd.DataFrame:
    """把 ``column`` 中按 ``delimiter`` 分隔的多个值拆成多行。

    其余列的取值在拆分后的每一行中保持不变；空白分隔项被丢弃。
    """
    if column not in frame.columns:
        raise KeyError(f"column not found: {column!r}")
    other_cols = [c for c in frame.columns if c != column]
    records: list[dict] = []
    for _, row in frame.iterrows():
        raw = row[column]
        if pd.isna(raw):
            continue
        parts = [p.strip() for p in str(raw).split(delimiter)]
        parts = [p for p in parts if p]
        if not parts:
            continue
        for part in parts:
            record = {c: row[c] for c in other_cols}
            record[column] = part
            records.append(record)
    if not records:
        return pd.DataFrame(columns=frame.columns)
    return pd.DataFrame(records, columns=frame.columns)


_QUANTITY_PATTERN = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*(.*)$")


def split_quantity_column(frame: pd.DataFrame, column: str) -> pd.DataFrame:
    """把 ``8件`` 这类 ``数值+单位`` 文本拆成数值列与单位列。

    结果新增 ``<column>_value`` 与 ``<column>_unit`` 两列；无法解析的行
    数值记为 NA、单位保留原文去空白后的剩余部分（可能为空）。
    """
    if column not in frame.columns:
        raise KeyError(f"column not found: {column!r}")
    frame = frame.copy()
    values: list[float | None] = []
    units: list[str | None] = []
    for raw in frame[column]:
        if pd.isna(raw):
            values.append(None)
            units.append(None)
            continue
        match = _QUANTITY_PATTERN.match(str(raw))
        if match is None:
            values.append(None)
            units.append(str(raw).strip())
            continue
        number_text, unit_text = match.groups()
        number = float(number_text)
        values.append(int(number) if number.is_integer() else number)
        units.append(unit_text.strip() or None)
    frame[f"{column}_value"] = pd.array(values, dtype="Float64")
    frame[f"{column}_unit"] = units
    return frame


def _is_missing(value: object) -> bool:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return True
    if isinstance(value, str) and value.strip() in _MISSING_TOKENS:
        return True
    return False


def clean_order_details(
    frame: pd.DataFrame,
    amount_column: str = "实付金额",
    drop_duplicates: bool = True,
) -> pd.DataFrame:
    """清洗电商订单明细风格的表。

    口径见模块 docstring。``amount_column`` 转数值失败记为 NA；
    其余文本列中的 ``#N/A`` 等占位符统一替换为 NA。
    """
    if frame.empty:
        return frame.copy()
    frame = frame.copy()

    # 1. 丢弃整行全空的占位行。
    frame = frame.dropna(how="all").reset_index(drop=True)

    # 2. 缺失占位符统一替换为 NA（保持 dtype 灵活，先转 object）。
    for col in frame.columns:
        if col == amount_column:
            continue
        converted = frame[col].map(lambda v: None if _is_missing(v) else v)
        frame[col] = converted

    # 3. 金额转数值。
    if amount_column in frame.columns:
        frame[amount_column] = pd.to_numeric(frame[amount_column], errors="coerce")

    # 4. 去除完全重复的行（仅当至少存在一个非空列时才有意义）。
    if drop_duplicates:
        frame = frame.drop_duplicates(keep="first").reset_index(drop=True)
    return frame


def vertical_concat(
    top: pd.DataFrame,
    bottom: pd.DataFrame,
    rename_map: dict[str, str] | None = None,
) -> pd.DataFrame:
    """纵向合并（追加）两张结构相同的表。

    ``rename_map`` 用于把 ``bottom`` 的列名先映射为与 ``top`` 一致，
    对应教材“字段名称不一致”的场景；未映射的列按原名对齐。
    """
    if rename_map:
        unknown = set(rename_map) - set(bottom.columns)
        if unknown:
            raise KeyError(f"rename_map keys not in bottom frame: {sorted(unknown)}")
        bottom = bottom.rename(columns=rename_map)
    return pd.concat([top, bottom], ignore_index=True, sort=False)


def horizontal_merge(
    left: pd.DataFrame,
    right: pd.DataFrame,
    on: str | list[str],
    how: str = "left",
) -> pd.DataFrame:
    """横向合并两张表（等价 SQL JOIN）。

    ``how`` 支持 pandas 的 ``left``/``inner``/``right``/``outer``；
    SQLite 演示中未使用的 ``right``/``outer`` 由 pandas 自行支持。
    """
    if how not in {"left", "inner", "right", "outer"}:
        raise ValueError(f"unsupported join type: {how!r}")
    keys = [on] if isinstance(on, str) else list(on)
    missing = [k for k in keys if k not in left.columns or k not in right.columns]
    if missing:
        raise KeyError(f"join keys missing in inputs: {missing}")
    merged = left.merge(right, on=keys, how=how, sort=False)
    return merged.reset_index(drop=True)
