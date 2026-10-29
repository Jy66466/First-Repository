# -*- coding: utf-8 -*-
"""
01_data_profiling.py —— Olist 原始数据实测核验（阶段2 · 交付给你亲自运行）

用途：
    数据下载解压后，第一时间摸清 9 个 CSV 的真实结构：行数、列数、列名、缺失率，
    并核验 4 个关键事实（订单时间范围、订单状态枚举、客户唯一 ID 数、订单级客户 ID 数）。

用法（在仓库根目录执行）：
    python tools/01_data_profiling.py
    # 若放别处，用完整路径执行亦可；脚本以"当前工作目录"下的 data/raw 为准

输出：
    1) 逐文件画像：行数、列数、列名、各列缺失率
    2) 核心字段核验：订单时间范围、状态分布、客户 ID 口径对比
    3) 结构核验（补充）：支付/明细/评价/地理表的"一单多行"情况
    4) 同时写一份日志到 logs/profiling_YYYYmmdd_HHMMSS.txt

注意：
    - 本脚本只读不写数据，不会修改 data/raw 下任何文件。
    - 不做任何清洗（缺失填补、去重、类型转换都留给 02_clean.py）。
    - 分块读取（chunk）以控制内存，地理表约百万行也不会撑爆。
"""

from __future__ import annotations

import contextlib
import sys
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd

# Windows 控制台默认 GBK，中文输出前先切 UTF-8，避免 UnicodeEncodeError
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

RAW_DIR = Path("data/raw")
LOG_DIR = Path("logs")
CHUNK_SIZE = 200_000  # 每块 20 万行，兼顾速度与内存

# 官方 9 个文件（用于检查是否齐全）
EXPECTED_FILES = [
    "olist_customers_dataset.csv",
    "olist_geolocation_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_order_payments_dataset.csv",
    "olist_order_reviews_dataset.csv",
    "olist_orders_dataset.csv",
    "olist_products_dataset.csv",
    "olist_sellers_dataset.csv",
    "product_category_name_translation.csv",
]


class Tee:
    """把 print 同时写到控制台和日志文件。"""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, text):
        for stream in self.streams:
            stream.write(text)

    def flush(self):
        for stream in self.streams:
            stream.flush()


def hr(char: str = "=", width: int = 78) -> None:
    print(char * width)


def profile_one_file(path: Path):
    """
    分块统计单个 CSV 的行数、列名、各列缺失数。
    返回 (行数, 列名列表, 缺失数 Series)；文件为空返回 (0, [], None)。
    """
    rows = 0
    columns: list[str] = []
    null_counts = None

    reader = pd.read_csv(
        path,
        chunksize=CHUNK_SIZE,
        encoding="utf-8-sig",
        low_memory=False,
    )
    for chunk in reader:
        if not columns:
            columns = list(chunk.columns)
            null_counts = chunk.isna().sum()
        else:
            null_counts = null_counts.add(chunk.isna().sum(), fill_value=0)
        rows += len(chunk)

    return rows, columns, null_counts


def print_file_profile(path: Path) -> dict:
    """打印一个文件的画像，并返回概要字典供后续汇总。"""
    hr("-")
    print(f"文件：{path.name}")

    try:
        rows, columns, null_counts = profile_one_file(path)
    except Exception as exc:
        print(f"  [读取失败] {exc.__class__.__name__}: {exc}")
        return {"file": path.name, "rows": None, "cols": None}

    if rows == 0 or null_counts is None:
        print("  [提示] 文件为空或无法解析表头")
        return {"file": path.name, "rows": 0, "cols": 0}

    print(f"  行数：{rows:,}    列数：{len(columns)}")
    print(f"  列名：{', '.join(columns)}")

    # 缺失率：只列有缺失的列，全部无缺失时给一句话
    missing = null_counts[null_counts > 0].sort_values(ascending=False)
    if missing.empty:
        print("  缺失：所有列均无缺失")
    else:
        print("  缺失情况：")
        for col, cnt in missing.items():
            rate = cnt / rows * 100
            print(f"    - {col:<42} 缺失 {int(cnt):>9,} 条（{rate:6.2f}%）")

    return {"file": path.name, "rows": rows, "cols": len(columns)}


def check_orders_core() -> None:
    """核验订单表的核心事实：时间范围、状态枚举、客户 ID 口径。"""
    hr()
    print("核心字段核验 · 订单表 olist_orders_dataset.csv")
    hr("-")

    path = RAW_DIR / "olist_orders_dataset.csv"
    if not path.exists():
        print("  [跳过] 文件不存在")
        return

    try:
        df = pd.read_csv(
            path,
            encoding="utf-8",
            low_memory=False,
            usecols=["order_id", "customer_id", "order_status", "order_purchase_timestamp"],
        )
    except Exception as exc:
        print(f"  [读取失败] {exc.__class__.__name__}: {exc}")
        print("  可能原因：列名与预期不一致（字段拼写问题），请对照上面的列名手工核对。")
        return

    # 1) 时间范围
    ts = pd.to_datetime(df["order_purchase_timestamp"], errors="coerce")
    bad_ts = int(ts.isna().sum())
    print(f"  订单总数                ：{len(df):,}")
    print(f"  order_purchase_timestamp 最早：{ts.min()}")
    print(f"  order_purchase_timestamp 最晚：{ts.max()}")
    print(f"  时间解析失败（NaT）条数 ：{bad_ts:,}")

    # 2) 状态枚举
    print("\n  订单状态分布（order_status）：")
    counts = df["order_status"].value_counts(dropna=False)
    for status, cnt in counts.items():
        label = "<空值>" if pd.isna(status) else status
        print(f"    {str(label):<16} {cnt:>9,} 条（{cnt / len(df) * 100:6.2f}%）")

    # 3) 客户 ID 口径
    print("\n  客户 ID 口径：")
    print(f"    customer_id 唯一值      ：{df['customer_id'].nunique():,}（订单级，每单一个）")
    print(f"    订单行数                ：{len(df):,}")
    # 同单多行检查（理论上 orders 表一单一行，若不等说明有重复记录）
    if len(df) != df["order_id"].nunique():
        print(f"    [异常] order_id 唯一值只有 {df['order_id'].nunique():,}，存在重复订单记录，需在清洗阶段处理")
    else:
        print("    order_id 唯一值         ：与行数一致（一单一行，符合预期）")


def check_customers_core() -> None:
    """核验客户表的 customer_unique_id 数量，并推算复购规模。"""
    hr()
    print("核心字段核验 · 客户表 olist_customers_dataset.csv")
    hr("-")

    path = RAW_DIR / "olist_customers_dataset.csv"
    if not path.exists():
        print("  [跳过] 文件不存在")
        return

    try:
        df = pd.read_csv(
            path,
            encoding="utf-8",
            low_memory=False,
            usecols=["customer_id", "customer_unique_id", "customer_state"],
        )
    except Exception as exc:
        print(f"  [读取失败] {exc.__class__.__name__}: {exc}")
        return

    n_cid = df["customer_id"].nunique()
    n_uid = df["customer_unique_id"].nunique()
    print(f"  客户表行数              ：{len(df):,}")
    print(f"  customer_id 唯一值      ：{n_cid:,}")
    print(f"  customer_unique_id 唯一值：{n_uid:,}")
    print(f"  两者差值                ：{n_cid - n_uid:,}（即「非首单」订单数的上界）")
    if n_uid:
        print(f"  推算复购客户占比上界    ：{(n_cid - n_uid) / n_uid * 100:.2f}%")
    print(f"  州数量                  ：{df['customer_state'].nunique()}（用于地理图）")
    print("\n  [说明] 该占比是上界估计：差值只说明「多出来的订单」，不等于复购客户数。")
    print("         真实复购客户数需在清洗阶段按 customer_unique_id 统计订单数后得出。")


def check_structure_extra() -> None:
    """
    补充结构核验：确认"一单多行"的四张表，避免清洗时金额被放大。
    这一节对应阶段1 风险清单里最常见的重复计算来源，建议不要删。
    """
    hr()
    print("结构核验（补充）：一单多行 / 一邮编多坐标")
    hr("-")

    # 支付表：一单可多行，直接求和会放大金额
    path = RAW_DIR / "olist_order_payments_dataset.csv"
    if path.exists():
        try:
            pay = pd.read_csv(path, encoding="utf-8-sig", low_memory=False, usecols=["order_id", "payment_value"])
            per_order = pay.groupby("order_id").size()
            print("  支付表 olist_order_payments_dataset.csv")
            print(f"    行数 {len(pay):,} / 订单数 {pay['order_id'].nunique():,}")
            print(f"    每单支付行数：最大 {per_order.max()}，平均 {per_order.mean():.2f}")
            print(f"    [结论] 直接 join 会把金额放大，须先按 order_id 汇总 payment_value")
        except Exception as exc:
            print(f"    支付表读取失败：{exc.__class__.__name__}: {exc}")

    # 明细表：一单多商品
    path = RAW_DIR / "olist_order_items_dataset.csv"
    if path.exists():
        try:
            items = pd.read_csv(path, encoding="utf-8-sig", low_memory=False, usecols=["order_id", "order_item_id"])
            per_order = items.groupby("order_id").size()
            print("\n  明细表 olist_order_items_dataset.csv")
            print(f"    行数 {len(items):,} / 订单数 {items['order_id'].nunique():,}")
            print(f"    每单商品行数：最大 {per_order.max()}，平均 {per_order.mean():.2f}")
            print("    [结论] 算「订单数/客单价」前须先聚合到订单级")
        except Exception as exc:
            print(f"    明细表读取失败：{exc.__class__.__name__}: {exc}")

    # 评价表：是否一单多评
    path = RAW_DIR / "olist_order_reviews_dataset.csv"
    if path.exists():
        try:
            rev = pd.read_csv(path, encoding="utf-8-sig", low_memory=False, usecols=["review_id", "order_id"])
            per_order = rev.groupby("order_id").size()
            multi = int((per_order > 1).sum())
            print("\n  评价表 olist_order_reviews_dataset.csv")
            print(f"    行数 {len(rev):,} / 订单数 {rev['order_id'].nunique():,} / review_id 唯一值 {rev['review_id'].nunique():,}")
            print(f"    存在多条评价的订单数：{multi:,}")
            print("    [结论] 若 >0，评分均值前须按订单去重（取最新一条）")
        except Exception as exc:
            print(f"    评价表读取失败：{exc.__class__.__name__}: {exc}")

    # 地理表：一邮编多坐标
    path = RAW_DIR / "olist_geolocation_dataset.csv"
    if path.exists():
        try:
            geo = pd.read_csv(
                path,
                encoding="utf-8",
                low_memory=False,
                usecols=["geolocation_zip_code_prefix", "geolocation_lat", "geolocation_lng"],
            )
            per_zip = geo.groupby("geolocation_zip_code_prefix").size()
            print("\n  地理表 olist_geolocation_dataset.csv")
            print(f"    行数 {len(geo):,} / 邮编前缀数 {len(per_zip):,}")
            print(f"    每前缀坐标数：最大 {per_zip.max()}，平均 {per_zip.mean():.2f}")
            print("    [结论] 直接关联会造成行数膨胀，须先按前缀取经纬度中位数聚合成 1 行")
        except Exception as exc:
            print(f"    地理表读取失败：{exc.__class__.__name__}: {exc}")


def main() -> int:
    LOG_DIR.mkdir(exist_ok=True)
    log_path = LOG_DIR / f"profiling_{datetime.now():%Y%m%d_%H%M%S}.txt"

    with open(log_path, "w", encoding="utf-8") as log_file:
        with contextlib.redirect_stdout(Tee(sys.stdout, log_file)):
            hr()
            print(f"Olist 数据实测核验    运行时间：{datetime.now():%Y-%m-%d %H:%M:%S}")
            print(f"工作目录：{Path.cwd()}")
            hr()

            if not RAW_DIR.exists():
                print(f"[错误] 找不到 {RAW_DIR.resolve()}")
                print("请确认：① 已在仓库根目录执行；② 数据已解压到 data/raw/ 下")
                print("下载命令：kaggle datasets download -d olistbr/brazilian-ecommerce -p data/raw --unzip")
                return 1

            # 0) 文件齐全性
            print("文件清单检查：")
            present = {p.name for p in RAW_DIR.glob("*.csv")}
            for name in EXPECTED_FILES:
                print(f"  {'[有]' if name in present else '[缺]'} {name}")
            extra = present - set(EXPECTED_FILES)
            if extra:
                print(f"  [多] 额外文件：{', '.join(sorted(extra))}")
            hr()

            # 1) 逐文件画像
            print("一、逐文件画像")
            summary = []
            for path in sorted(RAW_DIR.glob("*.csv")):
                summary.append(print_file_profile(path))

            # 2) 汇总表
            hr()
            print("汇总")
            hr("-")
            print(f"{'文件':<42}{'行数':>12}{'列数':>8}")
            for item in summary:
                rows = "-" if item["rows"] is None else f"{item['rows']:,}"
                cols = "-" if item["cols"] is None else str(item["cols"])
                print(f"{item['file']:<42}{rows:>12}{cols:>8}")

            # 3) 核心字段核验
            check_orders_core()
            check_customers_core()

            # 4) 补充结构核验
            check_structure_extra()

            # 5) 收尾
            hr()
            print("核验完成。请把本日志（logs/ 下）或控制台输出发给指导 Agent，用于回填数据字典。")
            print("下一步：确认字段无误后，再写 02_clean.py（本脚本不含任何清洗逻辑）。")
            hr()

    print(f"\n日志已保存：{log_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        print("\n[未捕获异常] 请把下面的信息一并反馈：")
        traceback.print_exc()
        raise SystemExit(1)
