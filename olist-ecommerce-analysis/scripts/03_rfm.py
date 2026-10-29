# -*- coding: utf-8 -*-
"""
================================================================================
03_rfm.py —— RFM 客户价值模型（八分类）
================================================================================

功能
    基于清洗后的订单主表，计算每个客户的 R / F / M 三个维度，
    按中位数（R、M）与业务断点（F）打分，映射为 8 类客户价值分群，
    并输出客户级明细表与分群汇总表。

输入
    data/clean/orders_clean.csv        主分析集（97,308 单；delivered+shipped，2017-01~2018-08）

输出
    outputs/tables/rfm.csv             客户级明细：customer_unique_id, R, F, M,
                                       R_score, F_score, M_score, Segment
    outputs/tables/rfm_summary.csv     分群汇总：Segment, 客户数, 客户数占比,
                                       GMV总额, GMV占比, 平均R, 平均F, 平均M
    logs/rfm_YYYYmmdd_HHMMSS.log       运行日志

口径（写论文时逐条引用，不得改动）
    客户粒度 : customer_unique_id（真实客户；customer_id 是订单级键，禁止用于聚合）
    R        : 快照日 − 该客户最后一次下单日（天），快照日 = 数据最大下单日 + 1 天
    F        : 该客户的去重订单数 nunique(order_id)
    M        : 该客户的支付总额 sum(payment_total)，含运费
    R 评分   : R ≤ 中位数 → 2（近期有购买）；否则 → 1
    M 评分   : M > 中位数 → 2（高贡献）；否则 → 1
    F 评分   : F = 1 → 1；F ≥ 2 → 2（业务断点，不用中位数——复购率仅 3.12%，
               中位数恒为 1，二分会让全部客户落到同一侧）

运行
    在仓库根目录执行： python scripts/03_rfm.py
================================================================================
"""

from __future__ import annotations

import contextlib
import sys
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd

# Windows 控制台默认 GBK，先切 UTF-8，避免中文输出报 UnicodeEncodeError
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
OUT_DETAIL = TABLE_DIR / "rfm.csv"
OUT_SUMMARY = TABLE_DIR / "rfm_summary.csv"

# 读写统一使用 utf-8-sig：写出的 CSV 用 Excel 双击不乱码；
# 读取时也能正确剥离 BOM，避免首列名带 \ufeff 导致取列失败。
CSV_ENCODING = "utf-8-sig"

# 蓝图：8 个分群的固定顺序与映射关系（元组顺序 R, F, M）
SEGMENT_MAP = {
    (2, 2, 2): "重要价值客户",
    (2, 1, 2): "重要发展客户",
    (1, 2, 2): "重要保持客户",
    (1, 1, 2): "重要挽留客户",
    (2, 2, 1): "一般价值客户",
    (2, 1, 1): "一般发展客户",
    (1, 2, 1): "一般保持客户",
    (1, 1, 1): "一般挽留客户",
}
SEGMENT_ORDER = list(SEGMENT_MAP.values())   # 汇总表按此顺序补齐，保证恒为 8 行

# 复盘单锁定的基准值（仅用于自检对比，不参与计算）
BASELINE_ORDERS = 97_308
BASELINE_CUSTOMERS = 96_096
BASELINE_REPEAT_RATE = 3.12

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
# 模块 2：读取与基础过滤
# ==============================================================================

def load_orders() -> pd.DataFrame:
    """
    读入主分析集并做最小必要的类型规整。
    只读，不修改 data/clean 下任何文件。
    """
    section("步骤 1 / 6　读入主分析集")

    if not ORDERS_FILE.exists():
        raise FileNotFoundError(f"缺少 {ORDERS_FILE}，请先运行 02_clean.py")

    df = pd.read_csv(ORDERS_FILE, encoding=CSV_ENCODING, low_memory=False)
    # 双保险：清理列名可能残留的 BOM
    df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]

    # 类型规整
    df["order_purchase_timestamp"] = pd.to_datetime(df["order_purchase_timestamp"], errors="coerce")
    df["payment_total"] = pd.to_numeric(df["payment_total"], errors="coerce").astype(float)
    df["customer_unique_id"] = df["customer_unique_id"].astype("string")

    # has_payment 兼容布尔/字符串两种读法
    if df["has_payment"].dtype != bool:
        df["has_payment"] = df["has_payment"].astype(str).str.lower().isin(["true", "1", "1.0"])

    log(f"  文件：{ORDERS_FILE}")
    log(f"  行数：{len(df):,}　客户唯一值：{df['customer_unique_id'].nunique():,}")
    log(f"  时间范围：{df['order_purchase_timestamp'].min()} ~ {df['order_purchase_timestamp'].max()}")
    log(f"  基准对照：orders_clean 应为 {BASELINE_ORDERS:,} 单，实际 {len(df):,} 单"
        + ("（一致）" if len(df) == BASELINE_ORDERS else "（与复盘单不一致，请核对）"))
    return df


def filter_valid_orders(df: pd.DataFrame) -> pd.DataFrame:
    """
    剔除无支付记录的订单。
    依据：M 维度依赖 payment_total；无支付订单若保留，会让客户 M=0 被误判为低价值。
    """
    section("步骤 2 / 6　剔除无支付记录订单")

    before = len(df)
    valid = df[df["has_payment"]].copy()
    dropped = before - len(valid)

    log(f"  剔除前：{before:,} 单")
    log(f"  无支付记录：{dropped:,} 单（全量数据中 payments 覆盖 99,440/99,441，主分析集内通常为 1 单或 0 单）")
    log(f"  参与计算的订单：{len(valid):,} 单")

    if dropped > 5:
        raise ValueError(f"剔除 {dropped} 单异常偏多（预期 ≤1），请检查 has_payment 字段是否正确读取")

    # 客户 ID 必须是有效值，否则会被聚成一个虚假客户
    n_unknown = int((valid["customer_unique_id"].isna() | (valid["customer_unique_id"] == "unknown")).sum())
    log(f"  customer_unique_id 无效值：{n_unknown} 条")
    if n_unknown:
        raise ValueError(f"存在 {n_unknown} 条无效 customer_unique_id，请先回到 02_clean.py 排查关联")
    return valid


# ==============================================================================
# 模块 3：计算 R / F / M
# ==============================================================================

def compute_rfm(orders: pd.DataFrame) -> tuple[pd.DataFrame, pd.Timestamp]:
    """
    按 customer_unique_id 聚合出 R / F / M。
    R 的方向：数值越小 = 最近购买 = 越优质（R13，后面打分时不可搞反）。
    """
    section("步骤 3 / 6　计算 R / F / M")

    # 快照日 = 数据中最大下单日 + 1 天。
    # 用数据自身的最新日期而非"今天"，保证任何时间重跑结果完全一致（可复现）。
    last_order_date = orders["order_purchase_timestamp"].max()
    snapshot = (last_order_date + pd.Timedelta(days=1)).normalize()
    log(f"  数据最大下单时间：{last_order_date}")
    log(f"  快照日（Snapshot）：{snapshot.date()}　＝ 最大下单日 + 1 天")

    grouped = orders.groupby("customer_unique_id", observed=True)
    rfm = grouped.agg(
        last_order_ts=("order_purchase_timestamp", "max"),
        F=("order_id", "nunique"),              # 去重订单数：一单多商品不会被放大
        M=("payment_total", "sum"),             # 仅取 payments 汇总口径，不与商品金额相加
    ).reset_index()

    # R：快照日 − 最后下单日（自然日）
    rfm["R"] = (snapshot - rfm["last_order_ts"].dt.normalize()).dt.days

    # 类型与合法性
    rfm["R"] = rfm["R"].astype("int64")
    rfm["F"] = rfm["F"].astype("int64")
    rfm["M"] = rfm["M"].astype(float).round(2)

    if (rfm["R"] < 0).any():
        raise ValueError("存在 R < 0 的客户，说明快照日计算有误")
    if (rfm["M"] < 0).any():
        raise ValueError("存在 M < 0 的客户，说明 payment_total 含异常值")

    log(f"  客户数：{len(rfm):,}")
    log(f"  R 区间：{rfm['R'].min()} ~ {rfm['R'].max()} 天　中位数 {rfm['R'].median():.0f} 天")
    log(f"  F 区间：{rfm['F'].min()} ~ {rfm['F'].max()} 单　均值 {rfm['F'].mean():.3f} 单")
    log(f"  M 区间：{rfm['M'].min():,.2f} ~ {rfm['M'].max():,.2f}　总额 {rfm['M'].sum():,.2f}")
    log(f"  M 中位数：{rfm['M'].median():,.2f}")

    # R7：客户数应不超过全量唯一客户数；若相等反而说明没做窗口过滤
    if len(rfm) > BASELINE_CUSTOMERS:
        raise ValueError(f"RFM 客户数 {len(rfm):,} 超过全量客户数 {BASELINE_CUSTOMERS:,}，客户粒度可能用错")
    log(f"  [校验] 客户数 ≤ {BASELINE_CUSTOMERS:,} ✓（{len(rfm):,}）")
    if len(rfm) == BASELINE_CUSTOMERS:
        log("  [提示] 客户数与全量完全相等，请确认窗口过滤是否生效（一般应略少）")

    return rfm, snapshot


# ==============================================================================
# 模块 4：打分与八分类
# ==============================================================================

def score_and_segment(rfm: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    按复盘单口径打分并映射 8 类。
    R：R ≤ 中位数 → 2（近期活跃）；否则 1
    M：M > 中位数 → 2（高贡献）；否则 1
    F：F = 1 → 1；F ≥ 2 → 2（业务断点，不用中位数）
    """
    section("步骤 4 / 6　打分与八分类")

    # 阈值：中位数（金额与时长右偏，中位数抗极值）
    r_median = rfm["R"].median()
    m_median = rfm["M"].median()
    log(f"  R 中位数（切分阈值）：{r_median:.1f} 天")
    log(f"  M 中位数（切分阈值）：{m_median:,.2f}")

    # R13：R 越小越好，所以 <= 中位数 记 2 分
    rfm["R_score"] = (rfm["R"] <= r_median).map({True: 2, False: 1}).astype("int64")
    # M 越大越好，所以 > 中位数 记 2 分
    rfm["M_score"] = (rfm["M"] > m_median).map({True: 2, False: 1}).astype("int64")
    # R15：F 用业务断点，绝不能用中位数
    rfm["F_score"] = (rfm["F"] >= 2).map({True: 2, False: 1}).astype("int64")

    # F 分布（为论文"退化"论述提供数字）
    f1 = int((rfm["F"] == 1).sum())
    f2 = int((rfm["F"] >= 2).sum())
    log(f"  F 分布：购买 1 单 {f1:,} 户（{f1 / len(rfm) * 100:.2f}%）　"
        f"购买 ≥2 单 {f2:,} 户（{f2 / len(rfm) * 100:.2f}%）")

    # 八分类映射
    keys = [(int(r), int(f), int(m)) for r, f, m in zip(rfm["R_score"], rfm["F_score"], rfm["M_score"])]
    rfm["Segment"] = [SEGMENT_MAP.get(k, "未分类") for k in keys]

    n_unmapped = int((rfm["Segment"] == "未分类").sum())
    if n_unmapped:
        raise ValueError(f"有 {n_unmapped} 户未能映射到 8 类，打分列取值异常")

    log("  八分类映射完成（元组顺序 R, F, M）：")
    for key, name in SEGMENT_MAP.items():
        n = int((rfm["Segment"] == name).sum())
        log(f"    {key} → {name:<8} {n:>7,} 户（{n / len(rfm) * 100:5.2f}%）")

    # R17/R18：披露结构失衡，不修饰
    f2_share = f2 / len(rfm) * 100
    log("")
    log(f"  [结构提示] F=2 的 4 类合计仅占 {f2_share:.2f}%，单类不足 {f2_share / 4:.2f}%。")
    log("  [结构提示] 这是平台复购率极低导致的真实结构，八分类实质接近 R×M 四象限的细分，")
    log("             论文应如实说明该退化，不得合并类别或剔除一次性客户来美化分布。")

    thresholds = {
        "r_median": float(r_median),
        "m_median": float(m_median),
        "f1": f1,
        "f2": f2,
    }
    return rfm, thresholds


# ==============================================================================
# 模块 5：汇总与导出
# ==============================================================================

def build_summary(rfm: pd.DataFrame) -> pd.DataFrame:
    """按 Segment 汇总，并强制补齐 8 行（即使某类为 0 户也不丢类）。"""
    section("步骤 5 / 6　分群汇总")

    total_customers = len(rfm)
    total_gmv = float(rfm["M"].sum())

    agg = rfm.groupby("Segment", observed=True).agg(
        客户数=("customer_unique_id", "count"),
        GMV总额=("M", "sum"),
        平均R=("R", "mean"),
        平均F=("F", "mean"),
        平均M=("M", "mean"),
    ).reindex(SEGMENT_ORDER)

    # 补齐 0 户的类别（计数补 0，均值留空，避免把"无客户"写成 0 元均值）
    agg["客户数"] = agg["客户数"].fillna(0).astype("int64")
    agg["GMV总额"] = agg["GMV总额"].fillna(0.0).astype(float)

    agg["客户数占比"] = (agg["客户数"] / total_customers * 100).round(2)
    agg["GMV占比"] = (agg["GMV总额"] / total_gmv * 100).round(2)
    for col in ["GMV总额", "平均R", "平均F", "平均M"]:
        agg[col] = agg[col].round(2)

    summary = agg.reset_index().rename(columns={"index": "Segment"})
    summary = summary[["Segment", "客户数", "客户数占比", "GMV总额", "GMV占比", "平均R", "平均F", "平均M"]]
    summary = summary.sort_values("GMV总额", ascending=False).reset_index(drop=True)

    log(f"  分群数：{len(summary)}（应为 8）")
    log("")
    log(f"  {'分群':<10}{'客户数':>9}{'客户占比':>10}{'GMV':>14}{'GMV占比':>10}")
    log("  " + "-" * 58)
    for _, row in summary.iterrows():
        log(f"  {row['Segment']:<10}{row['客户数']:>9,}{row['客户数占比']:>9.2f}%{row['GMV总额']:>14,.2f}{row['GMV占比']:>9.2f}%")

    return summary


def export(rfm: pd.DataFrame, summary: pd.DataFrame) -> None:
    """导出两张表（utf-8-sig，Excel 可直接打开）。"""
    section("步骤 6 / 6　导出")

    TABLE_DIR.mkdir(parents=True, exist_ok=True)

    detail = rfm[["customer_unique_id", "R", "F", "M", "R_score", "F_score", "M_score", "Segment"]].copy()
    detail = detail.sort_values(["Segment", "M"], ascending=[True, False]).reset_index(drop=True)
    detail.to_csv(OUT_DETAIL, index=False, encoding=CSV_ENCODING)
    log(f"  客户级明细 → {OUT_DETAIL}（{len(detail):,} 行 × {detail.shape[1]} 列）")

    summary.to_csv(OUT_SUMMARY, index=False, encoding=CSV_ENCODING)
    log(f"  分群汇总　 → {OUT_SUMMARY}（{len(summary)} 行 × {summary.shape[1]} 列）")


# ==============================================================================
# 模块 7：自检（不通过直接抛错，避免脏结果流到下游）
# ==============================================================================

def self_check(rfm: pd.DataFrame, summary: pd.DataFrame, orders: pd.DataFrame) -> None:
    section("自检")

    # 1) 客户主键唯一
    dup = int(rfm.duplicated(subset=["customer_unique_id"]).sum())
    if dup:
        raise AssertionError(f"rfm 中 customer_unique_id 存在 {dup} 条重复")
    log(f"  [1/5] customer_unique_id 唯一 ✓（{len(rfm):,} 户）")

    # 2) 八类客户数合计 = 总客户数（不能丢人）
    n_sum = int(summary["客户数"].sum())
    if n_sum != len(rfm):
        raise AssertionError(f"八类客户数合计 {n_sum:,} ≠ RFM 客户数 {len(rfm):,}")
    log(f"  [2/5] 八类客户数合计 = {n_sum:,} ✓")

    # 3) M 总额与订单表支付总额交叉校验（误差 < 1 元）
    m_rfm = float(rfm["M"].sum())
    m_src = float(orders["payment_total"].sum())
    diff = abs(m_rfm - m_src)
    log(f"  [3/5] rfm['M'].sum() = {m_rfm:,.2f}")
    log(f"        orders_clean[has_payment].payment_total.sum() = {m_src:,.2f}")
    log(f"        差额 = {diff:.4f} 元")
    if diff >= 1:
        raise AssertionError(f"M 总额与订单表支付总额差 {diff:.2f} 元（阈值 <1 元），存在漏算或重复计入")

    # 4) F 与订单数一致（抽样口径校验：F 之和应等于参与计算的订单数）
    n_orders = int(orders["order_id"].nunique())
    f_sum = int(rfm["F"].sum())
    if f_sum != n_orders:
        raise AssertionError(f"F 之和 {f_sum:,} ≠ 参与计算的订单数 {n_orders:,}，F 口径可能有误")
    log(f"  [4/5] F 之和 = {f_sum:,} = 参与计算订单数 ✓")

    # 5) 复购率交叉校验（R22：预期低于 3.12%，需解释而非修正）
    repeat_rate = float((rfm["F"] >= 2).mean() * 100)
    log(f"  [5/5] 本表口径复购率 = {repeat_rate:.2f}%（基准 {BASELINE_REPEAT_RATE:.2f}%）")
    if repeat_rate > BASELINE_REPEAT_RATE + 1.0:
        raise AssertionError(
            f"复购率 {repeat_rate:.2f}% 明显高于全量基准 {BASELINE_REPEAT_RATE}%（超过 1 个百分点），"
            "不符合窗口过滤方向，请检查是否误用了全量客户表"
        )
    if repeat_rate > BASELINE_REPEAT_RATE:
        log("        提示：略高于全量基准，通常源于 2016 年「仅首购」客户被移出分母，属口径差异，论文需说明。")
    else:
        log("        说明：窗口过滤会把「2016 首购 + 窗口内复购」的客户截成单次购买，")
        log("              故本口径复购率略低于全量 3.12% 属预期偏差，论文需注明，不得放宽窗口去凑数。")


# ==============================================================================
# 主流程
# ==============================================================================

def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"rfm_{datetime.now():%Y%m%d_%H%M%S}.log"

    with open(log_path, "w", encoding="utf-8") as log_file:
        with contextlib.redirect_stdout(Tee(sys.stdout, log_file)):
            log("=" * 78)
            log(f"03_rfm.py 运行时间：{datetime.now():%Y-%m-%d %H:%M:%S}")
            log(f"工作目录：{Path.cwd()}")
            log("=" * 78)

            orders = load_orders()
            valid = filter_valid_orders(orders)
            rfm, snapshot = compute_rfm(valid)
            rfm, thresholds = score_and_segment(rfm)
            summary = build_summary(rfm)

            export(rfm, summary)
            self_check(rfm, summary, valid)

            section("完成")
            log(f"  快照日：{snapshot.date()}")
            log(f"  R 阈值：{thresholds['r_median']:.1f} 天　M 阈值：{thresholds['m_median']:,.2f}")
            log(f"  客户数：{len(rfm):,}　复购客户：{thresholds['f2']:,} 户")
            log(f"  日志：{log_path}")
            log("  下一步：核对 rfm_summary.csv 的 GMV 占比结构，再进入 04_cohort.py")

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
