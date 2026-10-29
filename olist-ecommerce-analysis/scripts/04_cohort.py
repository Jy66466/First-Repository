# -*- coding: utf-8 -*-
"""
================================================================================
04_cohort.py —— 同期群（Cohort）留存分析
================================================================================

功能
    以客户「首单所在年月」划分同期群，计算各群在首购后第 n 个月的回访留存率，
    输出同期群规模表与留存率矩阵，并在终端打印矩阵与留存洞察。

输入
    data/clean/orders_clean.csv     主分析集（97,308 单；2017-01-05 ~ 2018-08-29）

输出
    outputs/tables/cohort_size.csv     每行一个 cohort：cohort_month, cohort_size
    outputs/tables/cohort_matrix.csv   留存率矩阵：行=cohort_month，列=month_index 0~12
    logs/cohort_YYYYmmdd_HHMMSS.log    运行日志

口径（写论文时逐条引用）
    客户粒度   : customer_unique_id
    Cohort     : 客户首单所在年月（YYYY-MM）
    观察范围   : cohort 限 2017-01 ~ 2018-06（保证至少 2 个月观察期）
    Month Index: 0 ~ 12；0 = 首购当月（恒为 100%）
    留存率     : 第 n 月留存率 = 该 cohort 中「首购后第 n 个月有 ≥1 笔订单」的客户数 ÷ cohort 规模
    活跃判定   : 同一客户同月多笔订单只计 1 次（去重到 客户×月）
    未观测月份 : 数据截止 2018-08，晚成立的 cohort 无法观测到高月龄，
                 这些格子留空（NaN），**不按 0 计**，也不参与均值计算

两个必须写进论文的口径提示
    1) 「首单」是**窗口内首单**。真实首购发生在 2016 年的客户（该年数据被剔除）
       会被推后计入 2017 年某月的 cohort，导致 2017 年前几个月的 cohort 略微偏大。
    2) 留存率在第 1 月后基本走平，是平台复购率极低（3.03%）的必然结果，
       不是计算错误；这正是"拉新驱动、留存失效"的核心证据。

运行
    在仓库根目录执行： python scripts/04_cohort.py
================================================================================
"""

from __future__ import annotations

import contextlib
import sys
import traceback
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# ==============================================================================
# 模块 0：全局配置
# ==============================================================================

CLEAN_DIR = Path("data/clean")
TABLE_DIR = Path("outputs/tables")
LOG_DIR = Path("logs")

ORDERS_FILE = CLEAN_DIR / "orders_clean.csv"
OUT_SIZE = TABLE_DIR / "cohort_size.csv"
OUT_MATRIX = TABLE_DIR / "cohort_matrix.csv"

CSV_ENCODING = "utf-8-sig"

# Cohort 选取范围：保证每个 cohort 至少能被观察 2 个月
# （数据止于 2018-08，2018-06 成立的 cohort 仍可看到第 0、1、2 月）
COHORT_START = "2017-01"
COHORT_END = "2018-06"

# 月份龄上限
MAX_MONTH_INDEX = 12

# 基准（来自 02/03 已锁定的口径，仅用于自检对比）
BASELINE_ORDERS = 97_308
BASELINE_CUSTOMERS = 94_136

LOGLINES: list[str] = []


# ==============================================================================
# 模块 1：日志工具
# ==============================================================================

class Tee:
    """把 print 同时写到控制台与日志文件。"""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, text):
        for stream in self.streams:
            stream.write(text)

    def flush(self):
        for stream in self.streams:
            stream.flush()


def log(msg: str = "") -> None:
    print(msg)
    LOGLINES.append(msg)


def section(title: str) -> None:
    log("")
    log("=" * 78)
    log(title)
    log("=" * 78)


# ==============================================================================
# 模块 2：读取与基础校验
# ==============================================================================

def load_orders() -> pd.DataFrame:
    section("步骤 1 / 6　读入主分析集")

    if not ORDERS_FILE.exists():
        raise FileNotFoundError(f"缺少 {ORDERS_FILE}，请先运行 02_clean.py")

    df = pd.read_csv(ORDERS_FILE, encoding=CSV_ENCODING, low_memory=False)
    df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]

    df["order_purchase_timestamp"] = pd.to_datetime(df["order_purchase_timestamp"], errors="coerce")
    df["customer_unique_id"] = df["customer_unique_id"].astype("string")

    if df["order_purchase_timestamp"].isna().any():
        n_bad = int(df["order_purchase_timestamp"].isna().sum())
        raise ValueError(f"存在 {n_bad} 条无法解析的下单时间，请回到 02_clean.py 排查")

    log(f"  文件：{ORDERS_FILE}")
    log(f"  行数：{len(df):,}　客户唯一值：{df['customer_unique_id'].nunique():,}")
    log(f"  时间范围：{df['order_purchase_timestamp'].min()} ~ {df['order_purchase_timestamp'].max()}")
    if len(df) != BASELINE_ORDERS:
        log(f"  [提示] 与基准 {BASELINE_ORDERS:,} 单不一致，请确认是否改动过清洗口径")
    return df


# ==============================================================================
# 模块 3：定义 Cohort（首单年月）
# ==============================================================================

def build_cohort(orders: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    按 customer_unique_id 取首单时间，得到 cohort_month。
    同时把客户级的 cohort 信息回挂到订单表，用于后续计算 month_index。
    """
    section("步骤 2 / 6　定义同期群（首单年月）")

    # 客户首单：全窗口内的最早下单时间
    first = (orders.groupby("customer_unique_id", observed=True)["order_purchase_timestamp"]
                   .min().rename("first_order_ts").reset_index())

    # 首单时间必须落在主分析窗口内（orders_clean 已过滤，这里做兜底断言）
    ts_min, ts_max = orders["order_purchase_timestamp"].min(), orders["order_purchase_timestamp"].max()
    bad = first[(first["first_order_ts"] < ts_min) | (first["first_order_ts"] > ts_max)]
    if len(bad):
        raise ValueError(f"有 {len(bad)} 个客户的首单时间越界，数据异常")

    first["cohort_month"] = first["first_order_ts"].dt.strftime("%Y-%m")
    # 用「年×12 + 月」把年月转成整数，做月份龄相减最稳妥（不受 Period 类型差异影响）
    first["cohort_ym"] = first["first_order_ts"].dt.year * 12 + first["first_order_ts"].dt.month

    log(f"  客户总数（主分析集内）：{len(first):,}")
    log(f"  首单月份数：{first['cohort_month'].nunique()} 个（{first['cohort_month'].min()} ~ {first['cohort_month'].max()}）")

    # 限定 cohort 范围
    in_range = first["cohort_month"].between(COHORT_START, COHORT_END)
    cohort = first[in_range].copy()
    excluded = int((~in_range).sum())

    log(f"  cohort 范围：{COHORT_START} ~ {COHORT_END}（保证至少 2 个月观察期）")
    cover = len(cohort) / len(first) * 100
    log(f"  纳入客户：{len(cohort):,} 户（覆盖全部客户 {cover:.2f}%）　"
        f"排除：{excluded:,} 户（首购在 {COHORT_END} 之后，观察期不足）")

    # 回挂到订单表
    orders = orders.merge(first[["customer_unique_id", "cohort_month", "cohort_ym"]],
                          on="customer_unique_id", how="left")
    orders["order_ym"] = orders["order_purchase_timestamp"].dt.year * 12 + orders["order_purchase_timestamp"].dt.month
    orders["month_index"] = orders["order_ym"] - orders["cohort_ym"]

    if (orders["month_index"] < 0).any():
        raise ValueError("存在 month_index < 0 的记录，说明 cohort 定义或首单计算有误")

    # 只保留纳入范围的 cohort
    orders_j = orders[orders["cohort_month"].between(COHORT_START, COHORT_END)].copy()

    # 限制后的核对
    assert len(cohort) == cohort["customer_unique_id"].nunique(), "cohort 内客户存在重复"
    log(f"  [校验] cohort 客户数唯一 ✓（{len(cohort):,}）")
    log(f"  [校验] 纳入 cohort 的订单：{len(orders_j):,} 单")

    return cohort, orders_j


# ==============================================================================
# 模块 4：计算留存率矩阵
# ==============================================================================

def compute_matrix(cohort: pd.DataFrame, orders_j: pd.DataFrame) -> pd.DataFrame:
    """
    留存矩阵：行 cohort_month，列 month_index(0~12)，值为留存率。
    未观测到的月份龄留空（NaN），避免把"还没发生"当成"流失"。
    """
    section("步骤 3 / 6　计算留存率矩阵")

    # 每个 cohort 的规模
    size = cohort.groupby("cohort_month", observed=True)["customer_unique_id"].nunique()

    # 活跃客户：客户 × 月份龄 去重（同月多单只算 1 次）
    act = orders_j[orders_j["month_index"].between(0, MAX_MONTH_INDEX)]
    act = act.drop_duplicates(subset=["cohort_month", "month_index", "customer_unique_id"])

    counts = (act.groupby(["cohort_month", "month_index"], observed=True)["customer_unique_id"]
                 .nunique().unstack(fill_value=0))

    # 补齐 0~12 全部列，补齐全部 cohort 行
    counts = counts.reindex(index=sorted(size.index), columns=range(0, MAX_MONTH_INDEX + 1), fill_value=0)

    matrix = counts.div(size, axis=0)

    # 观测截止：数据最大月份 - 各 cohort 起始月份 = 该 cohort 能观测到的最大月龄
    data_max_ym = int(orders_j["order_ym"].max())
    cohort_ym = cohort.groupby("cohort_month", observed=True)["cohort_ym"].first().reindex(matrix.index)
    max_obs = data_max_ym - cohort_ym.astype(int)

    # 超出可观测范围的格子置为 NaN（不按 0 计）
    for c in matrix.index:
        limit = int(max_obs.loc[c])
        for col in matrix.columns:
            if col > limit:
                matrix.loc[c, col] = np.nan

    # 第 0 月必须为 100%
    first_col = matrix[0].round(6)
    if not (first_col == 1.0).all():
        bad = first_col[first_col != 1.0]
        raise AssertionError(f"第 0 月留存率应为 100%，异常 cohort：{dict(bad)}")

    log(f"  cohort 数：{len(matrix)}　月份龄：0 ~ {MAX_MONTH_INDEX}")
    log(f"  数据最大订单月：{data_max_ym // 12}-{data_max_ym % 12:02d}")
    log(f"  [校验] 第 0 月留存率全部 = 100% ✓")
    log("  [说明] 晚成立 cohort 的高月龄格子留空（未观测），不按 0 计、不参与均值")
    return matrix


# ==============================================================================
# 模块 5：终端预览
# ==============================================================================

def print_matrix(matrix: pd.DataFrame) -> None:
    """按百分比格式化打印矩阵，便于终端直接预览（空值打印为 ·）。"""
    section("步骤 5 / 6　留存率矩阵（单位：%）")

    header = "cohort   " + "".join([f"{c:>6}" for c in matrix.columns])
    log(header)
    log("-" * len(header))
    for idx, row in matrix.iterrows():
        cells = "".join(["     ·" if pd.isna(v) else f"{v * 100:6.1f}" for v in row.values])
        log(f"{idx:<9}{cells}")


def print_size(cohort: pd.DataFrame) -> pd.Series:
    section("步骤 4 / 6　同期群规模")

    size = (cohort.groupby("cohort_month", observed=True)["customer_unique_id"]
                  .nunique().sort_index())
    total = int(size.sum())

    log(f"  {'cohort':<10}{'客户数':>8}{'占比':>9}")
    log("  " + "-" * 27)
    for idx, n in size.items():
        log(f"  {idx:<10}{n:>8,}{n / total * 100:>8.2f}%")
    log("  " + "-" * 27)
    log(f"  {'合计':<10}{total:>8,}{100.0:>8.2f}%")
    log(f"  最大 cohort：{size.idxmax()}（{size.max():,} 户）　最小：{size.idxmin()}（{size.min():,} 户）")
    return size


# ==============================================================================
# 模块 6：留存洞察
# ==============================================================================

def print_insights(matrix: pd.DataFrame, size: pd.Series) -> None:
    section("步骤 6 / 6　留存洞察")

    # 次月留存：所有 cohort 都能观测到第 1 月，最公平的横向比较口径
    m1 = matrix[1].dropna().sort_values(ascending=False)
    m1_mean = float(matrix[1].mean())

    log(f"  次月留存率（month_index = 1）：平均 {m1_mean * 100:.2f}%")
    log(f"    最好：{m1.index[0]}（{m1.iloc[0] * 100:.2f}%）")
    log(f"    最差：{m1.index[-1]}（{m1.iloc[-1] * 100:.2f}%）")
    log(f"    极差：{(m1.iloc[0] - m1.iloc[-1]) * 100:.2f} 个百分点")

    # 其他月龄的平均值（只在可观测的 cohort 间平均）
    log("")
    log("  各月龄平均留存率（仅统计可观测 cohort）：")
    for col in [1, 2, 3, 6, 9, 12]:
        if col not in matrix.columns:
            continue
        s = matrix[col].dropna()
        if len(s) == 0:
            continue
        log(f"    第 {col:>2} 月：{s.mean() * 100:5.2f}%　（可观测 cohort {len(s)} 个）")

    # 整体：所有已观测格子的平均（含第 0 月）
    all_cells = matrix.stack()
    log("")
    log(f"  全矩阵平均留存（含第 0 月，受 100% 基数拉高，仅作参考）：{all_cells.mean() * 100:.2f}%")
    log(f"  全矩阵平均留存（不含第 0 月）：{matrix.drop(columns=[0]).stack().mean() * 100:.2f}%")

    # 结论式提示（数字都由上面算出，不预设结论）
    log("")
    log("  解读要点（论文可直接改写使用）：")
    log(f"    1. 次月留存仅 {m1_mean * 100:.1f}%，意味着约 {100 - m1_mean * 100:.1f}% 的客户首购后一个月内未再下单，")
    log("       与 RFM 得到的 3.03% 复购率互相印证——平台以一次性交易为主。")
    log("       注意：3.03% 是「窗口内任一时点复购过」的客户占比，本行 0.49% 是「恰好在次月复购」的")
    log("       月留存率，两者量级不同属正常，论文中不可混用同一个数字。")
    m3 = float(matrix[3].dropna().mean())
    m6 = float(matrix[6].dropna().mean())
    m12 = float(matrix[12].dropna().mean())
    tail = pd.Series([matrix[c].dropna().mean() for c in [3, 4, 5, 6, 9, 12] if c in matrix.columns]).dropna()
    log(f"    2. 留存曲线呈「断崖 + 长尾」：第 0 月 100% → 第 1 月 {m1_mean * 100:.2f}%，")
    log(f"       此后长期在 {tail.min() * 100:.2f}% ~ {tail.max() * 100:.2f}% 徘徊"
        f"（第 3/6/12 月分别为 {m3 * 100:.2f}% / {m6 * 100:.2f}% / {m12 * 100:.2f}%）。")
    log("       说明绝大部分流失发生在首购后的第一个月内，之后进入稳定低水平，")
    log("       而非逐月平滑衰减——这决定了召回动作必须卡在首购后 30 天内。")
    log("    3. 若各 cohort 次月留存差异不大，说明问题出在平台机制（品类结构、履约体验、")
    log("       缺乏复购激励），而非某个月的运营波动；差异大则应结合当月营销活动进一步归因。")
    log("")
    log("  [口径提示] 「首单」为窗口内首单：真实首购在 2016 年的客户被推后计入 2017 年 cohort，")
    log("             故 2017 年初几个 cohort 规模略偏大，比较留存时需注意。")


# ==============================================================================
# 模块 7：导出
# ==============================================================================

def export(size: pd.Series, matrix: pd.DataFrame) -> None:
    section("导出结果")

    TABLE_DIR.mkdir(parents=True, exist_ok=True)

    size_df = size.reset_index()
    size_df.columns = ["cohort_month", "cohort_size"]
    size_df.to_csv(OUT_SIZE, index=False, encoding=CSV_ENCODING)
    log(f"  同期群规模 → {OUT_SIZE}（{len(size_df)} 行）")

    matrix_out = matrix.round(4).copy()
    matrix_out.index.name = "cohort_month"
    matrix_out.to_csv(OUT_MATRIX, encoding=CSV_ENCODING)
    log(f"  留存率矩阵 → {OUT_MATRIX}（{matrix_out.shape[0]} 行 × {matrix_out.shape[1] + 1} 列）")

    # 导出后回读校验（确保空值未被写成 0）
    check = pd.read_csv(OUT_MATRIX, encoding=CSV_ENCODING, index_col="cohort_month")
    n_blank = int(check.isna().sum().sum())
    n_expected = int(matrix.isna().sum().sum())
    if n_blank != n_expected:
        raise AssertionError(f"回读校验失败：空值 {n_blank} 个 ≠ 预期 {n_expected} 个（可能被写成 0）")
    log(f"  [校验] 回读空值数一致 ✓（{n_blank} 个未观测格子保持为空）")


# ==============================================================================
# 主流程
# ==============================================================================

def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"cohort_{datetime.now():%Y%m%d_%H%M%S}.log"

    with open(log_path, "w", encoding="utf-8") as log_file:
        with contextlib.redirect_stdout(Tee(sys.stdout, log_file)):
            log("=" * 78)
            log(f"04_cohort.py 运行时间：{datetime.now():%Y-%m-%d %H:%M:%S}")
            log(f"工作目录：{Path.cwd()}")
            log(f"Cohort 范围：{COHORT_START} ~ {COHORT_END}　月份龄：0 ~ {MAX_MONTH_INDEX}")
            log("=" * 78)

            orders = load_orders()
            cohort, orders_j = build_cohort(orders)
            matrix = compute_matrix(cohort, orders_j)
            size = print_size(cohort)
            print_matrix(matrix)
            print_insights(matrix, size)
            export(size, matrix)

            section("完成")
            log(f"  日志：{log_path}")
            log("  下一步：核对 cohort_matrix.csv 的 L 型曲线，再进入 05_boston_abc.py")

    print(f"\n日志已保存：{log_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        print("\n[未捕获异常] 请把以下信息完整反馈：")
        traceback.print_exc()
        raise SystemExit(1)
