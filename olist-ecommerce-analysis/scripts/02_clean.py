# -*- coding: utf-8 -*-
"""
================================================================================
02_clean.py —— Olist 原始数据清洗与治理（六项基础治理 ＋ 四表预聚合）
================================================================================

功能
    把 data/raw/ 下 9 个官方 CSV，清洗治理为 data/clean/ 下 6 张分析用宽表
    ＋1 张全状态订单表（供漏斗分析），并输出清洗汇总表与运行日志。

输入（只读，绝不修改）
    data/raw/olist_orders_dataset.csv
    data/raw/olist_order_items_dataset.csv
    data/raw/olist_order_payments_dataset.csv
    data/raw/olist_customers_dataset.csv
    data/raw/olist_products_dataset.csv
    data/raw/olist_sellers_dataset.csv
    data/raw/olist_order_reviews_dataset.csv
    data/raw/olist_geolocation_dataset.csv
    data/raw/product_category_name_translation.csv

输出
    data/clean/orders_clean.csv        一行一订单（主分析集）
    data/clean/items_clean.csv         一行一订单项
    data/clean/customers_clean.csv     一行一 customer_unique_id
    data/clean/payments_order.csv      一行一订单（支付已聚合）
    data/clean/reviews_order.csv       一行一订单（评价已去重）
    data/clean/geo_prefix.csv          一行一邮编前缀（坐标已聚合）
    data/clean/orders_all_status.csv   一行一订单（全状态，供漏斗）
    outputs/tables/clean_summary.csv   清洗汇总（前后行数、缺失率变化）
    logs/clean_YYYYmmdd_HHMMSS.log     运行日志

设计原则
    1. 先聚合、后关联：payments / reviews / geolocation 一律先压到目标粒度，
       再 left join，杜绝行数膨胀与金额放大。
    2. 关联一律 left join，保留主表全部记录；无匹配项标 unknown，不静默丢行。
    3. 异常值只标记、不删除（新增 is_*_outlier 布尔列），保证数据可追溯。
    4. 履约类日期缺失不填充（缺失本身即业务信息：未送达/未审批）。
    5. 全流程无随机、无抽样、无合成数据，同样输入必得同样输出。

运行
    在仓库根目录执行： python scripts/02_clean.py
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

# Windows 控制台默认 GBK，先切 UTF-8，避免中文输出报 UnicodeEncodeError
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# ==============================================================================
# 模块 0：全局配置（改这里即可调整口径，不要在函数里写死数字）
# ==============================================================================

RAW_DIR = Path("data/raw")
CLEAN_DIR = Path("data/clean")
TABLE_DIR = Path("outputs/tables")
LOG_DIR = Path("logs")

# CSV 读写编码：utf-8-sig 便于 Excel 直接双击打开不乱码。
# 下游脚本读取 clean 文件时，请同样使用 encoding="utf-8-sig"。
CSV_ENCODING = "utf-8-sig"

# 主分析时间窗（依据 profiling 实测：数据 2016-09-04 ~ 2018-10-17）
# 2016 年订单极稀疏（平台早期），2018-09 之后数据不完整（截断），均不纳入核心分析。
ANALYSIS_START = "2017-01-01"
ANALYSIS_END = "2018-08-31 23:59:59"

# 主分析保留的订单状态：delivered（已送达）＋ shipped（已发货在途）
MAIN_STATUS = ["delivered", "shipped"]

# 缺失品类统一标记
UNKNOWN = "unknown"

# 异常值识别参数
IQR_K = 1.5          # 金额用 IQR 1.5 倍
P99_Q = 0.99         # 运费/支付额用 99% 分位数

# 需要强制按字符串读取的字段（防止邮编前导 0 丢失、长 ID 被转成科学计数）
STR_COLS = {
    "olist_orders_dataset.csv": ["order_id", "customer_id"],
    "olist_order_items_dataset.csv": ["order_id", "product_id", "seller_id"],
    "olist_order_payments_dataset.csv": ["order_id", "payment_type"],
    "olist_customers_dataset.csv": ["customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_state", "customer_city"],
    "olist_products_dataset.csv": ["product_id", "product_category_name"],
    "olist_sellers_dataset.csv": ["seller_id", "seller_zip_code_prefix", "seller_state", "seller_city"],
    "olist_order_reviews_dataset.csv": ["review_id", "order_id"],
    "olist_geolocation_dataset.csv": ["geolocation_zip_code_prefix", "geolocation_state", "geolocation_city"],
    "product_category_name_translation.csv": ["product_category_name", "product_category_name_english"],
}

# 汇总表容器：每清洗一张表追加一条记录
SUMMARY: list[dict] = []
LOGLINES: list[str] = []


# ==============================================================================
# 模块 1：通用工具
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
    """统一打印入口（同时进日志文件）。"""
    print(msg)
    LOGLINES.append(msg)


def section(title: str) -> None:
    """打印分节标题，便于日志阅读。"""
    log("")
    log("=" * 78)
    log(title)
    log("=" * 78)


def read_raw(filename: str) -> pd.DataFrame:
    """
    读取原始 CSV：统一 UTF-8，强制字符串列，不改动原文件。
    参数 filename 为 data/raw 下的文件名（含 .csv）。
    """
    path = RAW_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"缺少原始文件：{path}，请先用 Kaggle CLI 下载并解压到 data/raw/")

    dtype = {col: "string" for col in STR_COLS.get(filename, [])}
    # 重点：必须用 utf-8-sig 读取。
    # 实测发现 product_category_name_translation.csv 的文件头带 UTF-8 BOM，
    # 若用 encoding="utf-8"，首列会被读成 "\ufeffproduct_category_name"，
    # 导致与商品表按品类关联时全部匹配失败、品类英文名整列退化为 unknown（静默出错）。
    df = pd.read_csv(path, encoding="utf-8-sig", low_memory=False, dtype=dtype)
    # 双保险：无论来源如何，统一清理列名中的 BOM 与首尾空格
    df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]
    return df


def na_rate(df: pd.DataFrame) -> pd.Series:
    """返回各列缺失率（%），保留两位小数。"""
    return (df.isna().mean() * 100).round(2)


def avg_na(df: pd.DataFrame, cols: list[str] | None = None) -> float:
    """返回指定列（默认全部列）的平均缺失率（%），用于汇总表。"""
    target = df[cols] if cols else df
    return round(float(target.isna().mean().mean() * 100), 2)


def normalize_zip(series: pd.Series) -> pd.Series:
    """
    邮编前缀标准化为 5 位字符串。
    原始数据中 CEP 前缀以整数存储（如 1037），前导 0 已丢失；
    巴西 CEP 前缀固定 5 位，故用 zfill(5) 还原为 01037，保证两表可对齐。
    """
    return series.astype("string").str.strip().str.zfill(5)


def add_iqr_flag(df: pd.DataFrame, col: str, flag_col: str, k: float = IQR_K) -> dict:
    """
    IQR 法标记极端值（只标记不删除）。
    上界 = Q3 + k*IQR；下界 = max(Q1 - k*IQR, 0)（金额不为负，故下界截到 0）。
    """
    q1, q3 = df[col].quantile([0.25, 0.75])
    iqr = q3 - q1
    upper = q3 + k * iqr
    lower = max(q1 - k * iqr, 0)
    df[flag_col] = ((df[col] > upper) | (df[col] < lower)).fillna(False)
    return {"q1": float(q1), "q3": float(q3), "lower": float(lower), "upper": float(upper), "n": int(df[flag_col].sum())}


def add_p99_flag(df: pd.DataFrame, col: str, flag_col: str, q: float = P99_Q) -> dict:
    """99% 分位数法标记极端值（只标记不删除）。"""
    thr = df[col].quantile(q)
    df[flag_col] = (df[col] > thr).fillna(False)
    return {"q": q, "threshold": float(thr), "n": int(df[flag_col].sum())}


def add_time_parts(df: pd.DataFrame, ts_col: str, prefix: str = "purchase") -> pd.DataFrame:
    """
    日期对齐：从时间戳派生年/季/月/年月/周几 等分析维度。
    统一放在订单分析主表与明细表上，避免后续每个模型各算一遍。
    """
    ts = pd.to_datetime(df[ts_col], errors="coerce")
    df[f"{prefix}_year"] = ts.dt.year.astype("Int64")
    df[f"{prefix}_quarter"] = ts.dt.quarter.astype("Int64")
    df[f"{prefix}_month"] = ts.dt.month.astype("Int64")
    df[f"{prefix}_ym"] = ts.dt.strftime("%Y-%m")
    df[f"{prefix}_weekday"] = ts.dt.day_of_week.astype("Int64")

    weekday_map = {0: "周一", 1: "周二", 2: "周三", 3: "周四", 4: "周五", 5: "周六", 6: "周日"}
    df[f"{prefix}_weekday_name"] = df[f"{prefix}_weekday"].map(weekday_map)
    return df


def record(table: str, rows_raw: int | None, rows_clean: int, note: str,
           na_before: float | None = None, na_after: float | None = None) -> None:
    """向清洗汇总表追加一条记录。"""
    SUMMARY.append({
        "table": table,
        "rows_raw": rows_raw,
        "rows_clean": rows_clean,
        "rows_dropped": (rows_raw - rows_clean) if rows_raw is not None else None,
        "avg_missing_pct_before": na_before,
        "avg_missing_pct_after": na_after,
        "note": note,
    })


def assert_unique(df: pd.DataFrame, subset: list[str], table: str) -> None:
    """主键唯一性断言：不唯一直接报错，避免脏数据流到下游。"""
    dup = int(df.duplicated(subset=subset).sum())
    if dup:
        raise ValueError(f"[{table}] 主键 {subset} 存在 {dup} 条重复，清洗未达标，已中止")
    log(f"  [校验] {table} 主键 {subset} 唯一 ✓")


# ==============================================================================
# 模块 2：读取原始数据（只读）
# ==============================================================================

def load_all() -> dict[str, pd.DataFrame]:
    """一次性读入 9 张原始表，并做基础类型规整。"""
    section("步骤 1 / 7　读取原始数据（只读，不修改原文件）")

    orders = read_raw("olist_orders_dataset.csv")
    items = read_raw("olist_order_items_dataset.csv")
    payments = read_raw("olist_order_payments_dataset.csv")
    customers = read_raw("olist_customers_dataset.csv")
    products = read_raw("olist_products_dataset.csv")
    sellers = read_raw("olist_sellers_dataset.csv")
    reviews = read_raw("olist_order_reviews_dataset.csv")
    geo = read_raw("olist_geolocation_dataset.csv")
    trans = read_raw("product_category_name_translation.csv")

    # 日期统一转 datetime（errors="coerce"：无法解析记为 NaT，后续统计缺失率）
    date_cols = [
        "order_purchase_timestamp", "order_approved_at",
        "order_delivered_carrier_date", "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ]
    for col in date_cols:
        orders[col] = pd.to_datetime(orders[col], errors="coerce")

    items["shipping_limit_date"] = pd.to_datetime(items["shipping_limit_date"], errors="coerce")
    reviews["review_creation_date"] = pd.to_datetime(reviews["review_creation_date"], errors="coerce")
    reviews["review_answer_timestamp"] = pd.to_datetime(reviews["review_answer_timestamp"], errors="coerce")

    # 金额统一 float（原始已是数值，这里显式声明，避免下游被推断成 int）
    for col in ["price", "freight_value"]:
        items[col] = pd.to_numeric(items[col], errors="coerce").astype(float)
    payments["payment_value"] = pd.to_numeric(payments["payment_value"], errors="coerce").astype(float)
    payments["payment_installments"] = pd.to_numeric(payments["payment_installments"], errors="coerce")

    # 邮编前缀：5 位字符串（还原前导 0）
    customers["customer_zip_code_prefix"] = normalize_zip(customers["customer_zip_code_prefix"])
    geo["geolocation_zip_code_prefix"] = normalize_zip(geo["geolocation_zip_code_prefix"])
    sellers["seller_zip_code_prefix"] = normalize_zip(sellers["seller_zip_code_prefix"])

    for name, df in [
        ("orders", orders), ("items", items), ("payments", payments), ("customers", customers),
        ("products", products), ("sellers", sellers), ("reviews", reviews), ("geolocation", geo),
        ("translation", trans),
    ]:
        log(f"  {name:<12} 行数 {len(df):>9,}　列数 {df.shape[1]:>2}")

    return {
        "orders": orders, "items": items, "payments": payments, "customers": customers,
        "products": products, "sellers": sellers, "reviews": reviews, "geo": geo, "trans": trans,
    }


# ==============================================================================
# 模块 3：四张一对多表预聚合（先聚合、后关联的核心）
# ==============================================================================

def build_payments(orders: pd.DataFrame, payments: pd.DataFrame) -> pd.DataFrame:
    """
    支付表 → 订单级汇总。
    依据：profiling 实测 103,886 行 / 99,440 个订单，每单最多 29 条支付记录，
         直接 join 会把金额放大数倍。
    """
    section("步骤 2 / 7　支付表预聚合（103,886 行 → 订单级）")
    rows_raw = len(payments)

    # 主支付方式：先计数再取每个订单出现次数最多的一种（并列时按字典序取第一个，保证可复现）
    type_cnt = (payments.groupby(["order_id", "payment_type"], observed=True)
                        .size().reset_index(name="cnt")
                        .sort_values(["order_id", "cnt", "payment_type"], ascending=[True, False, True]))
    main_type = type_cnt.drop_duplicates("order_id")[["order_id", "payment_type"]]
    main_type = main_type.rename(columns={"payment_type": "payment_type_main"})

    pay = payments.groupby("order_id", as_index=False).agg(
        payment_total=("payment_value", "sum"),
        payment_record_cnt=("payment_sequential", "count"),
        payment_type_cnt=("payment_type", "nunique"),
        payment_installments_mean=("payment_installments", "mean"),
    )
    pay = pay.merge(main_type, on="order_id", how="left")
    pay["payment_installments_mean"] = pay["payment_installments_mean"].round(2)

    # 异常标记：订单总支付金额 p99
    info = add_p99_flag(pay, "payment_total", "is_payment_outlier")
    log(f"  聚合后行数：{len(pay):,}（原始 {rows_raw:,} 行）")
    log(f"  支付覆盖订单：{pay['order_id'].nunique():,} / 订单表 {len(orders):,}")
    log(f"  is_payment_outlier：{info['n']:,} 条（阈值 P99 = {info['threshold']:.2f}）")

    missing_orders = set(orders["order_id"]) - set(pay["order_id"])
    log(f"  无支付记录的订单：{len(missing_orders):,} 条（left join 后 payment_total 记 0，并置 has_payment=False）")

    record("payments_order", rows_raw, len(pay), "按 order_id 聚合支付金额/方式数/分期均值", avg_na(payments), avg_na(pay))
    return pay


def build_items(items: pd.DataFrame, products: pd.DataFrame, trans: pd.DataFrame,
                orders: pd.DataFrame) -> pd.DataFrame:
    """
    订单明细 → 保留订单项粒度，左连商品表与品类翻译表。
    依据：112,650 行 / 98,666 个订单，每单最多 21 项，不可压缩成订单粒度（品类分析需要明细）。
    """
    section("步骤 3 / 7　订单明细关联商品与品类（保留订单项粒度）")
    rows_raw = len(items)

    # 去重：同一订单同一序号只应有一条
    items = items.drop_duplicates(subset=["order_id", "order_item_id"], keep="first").copy()
    na_before = avg_na(items)   # 记录关联前的缺失率基线

    # 商品表去重后关联（只取品类字段，控制列数）
    prod = products[["product_id", "product_category_name"]].drop_duplicates("product_id")
    items = items.merge(prod, on="product_id", how="left")

    # 品类翻译：缺失或翻译表未覆盖的统一记 unknown（不丢行、不改总量）
    trans = trans.drop_duplicates("product_category_name")
    items = items.merge(trans, on="product_category_name", how="left")
    items["product_category_name"] = items["product_category_name"].fillna(UNKNOWN)
    items["product_category_en"] = items["product_category_name_english"].fillna(UNKNOWN)
    items = items.drop(columns=["product_category_name_english"])

    # 补下单时间（用于年月维度）：只取时间列，避免把订单级金额带进来重复计算
    items = items.merge(orders[["order_id", "order_purchase_timestamp"]], on="order_id", how="left")
    items = add_time_parts(items, "order_purchase_timestamp", prefix="purchase")

    # 异常标记（只标记不删除）
    price_info = add_iqr_flag(items, "price", "is_price_outlier")
    freight_info = add_p99_flag(items, "freight_value", "is_freight_outlier")
    log(f"  明细行数：{len(items):,}（原始 {rows_raw:,}，去重后）")
    log(f"  覆盖订单：{items['order_id'].nunique():,} / 订单表 {len(orders):,}")
    log(f"  品类 unknown 占比：{(items['product_category_en'] == UNKNOWN).mean() * 100:.2f}%")
    log(f"  is_price_outlier：{price_info['n']:,} 条（IQR 上界 {price_info['upper']:.2f}）")
    log(f"  is_freight_outlier：{freight_info['n']:,} 条（P99 = {freight_info['threshold']:.2f}）")

    record("items_clean", rows_raw, len(items), "保留订单项粒度 + 商品/品类左连 + IQR/P99 异常标记", na_before, avg_na(items))
    return items


def build_reviews(reviews: pd.DataFrame) -> pd.DataFrame:
    """
    评价表 → 订单级去重，取最新一条。
    依据：99,224 行 / 98,673 个订单，review_id 唯一值仅 98,410（存在重复 ID），
         且有 547 个订单存在多条评价。
    """
    section("步骤 4 / 7　评价表去重（99,224 行 → 订单级）")
    rows_raw = len(reviews)

    # 第一层：review_id 去重（同一评价被重复写入）
    rev = reviews.drop_duplicates(subset=["review_id"], keep="last").copy()
    dup_by_id = rows_raw - len(rev)

    # 第二层：同一订单多条评价，按创建时间取最新（缺失时间排在最前，确保有时间的优先被保留）
    rev = rev.sort_values(["order_id", "review_creation_date", "review_answer_timestamp"], na_position="first")
    rev = rev.drop_duplicates(subset=["order_id"], keep="last").copy()

    log(f"  review_id 重复剔除：{dup_by_id:,} 条")
    log(f"  订单级去重后：{len(rev):,} 行 / {rev['order_id'].nunique():,} 个订单")
    log(f"  评分缺失：{int(rev['review_score'].isna().sum()):,} 条")

    record("reviews_order", rows_raw, len(rev), "review_id 去重 + 按订单取最新一条", avg_na(reviews), avg_na(rev))
    return rev


def build_geo(geo: pd.DataFrame) -> pd.DataFrame:
    """
    地理表 → 邮编前缀级坐标。
    依据：1,000,163 行 / 19,015 个前缀，平均每前缀 52.6 条坐标（最多 1146 条），
         直接关联必然行数膨胀。取经纬度中位数（抗离群点，比均值更稳）。
    """
    section("步骤 5 / 7　地理表聚合（1,000,163 行 → 邮编前缀级）")
    rows_raw = len(geo)

    geo_agg = geo.groupby("geolocation_zip_code_prefix", as_index=False).agg(
        lat=("geolocation_lat", "median"),
        lng=("geolocation_lng", "median"),
        geo_record_cnt=("geolocation_lat", "size"),
    ).rename(columns={"geolocation_zip_code_prefix": "zip_code_prefix"})

    log(f"  聚合后行数：{len(geo_agg):,}（原始 {rows_raw:,} 行，压缩 {rows_raw / len(geo_agg):.1f} 倍）")
    log(f"  坐标范围：lat [{geo_agg['lat'].min():.4f}, {geo_agg['lat'].max():.4f}]　lng [{geo_agg['lng'].min():.4f}, {geo_agg['lng'].max():.4f}]")

    record("geo_prefix", rows_raw, len(geo_agg), "按邮编前缀取经纬度中位数", avg_na(geo), avg_na(geo_agg))
    return geo_agg


# ==============================================================================
# 模块 4：客户维度表（一人一行）
# ==============================================================================

def build_customers(orders: pd.DataFrame, customers: pd.DataFrame, geo: pd.DataFrame) -> pd.DataFrame:
    """
    以 customer_unique_id 为主键聚合客户。
    口径：
      - 首单时间 = 该客户最早 order_purchase_timestamp
      - 地理信息取"首单的收货地址"（保持维度不膨胀）
      - 坐标通过首单邮编前缀关联 geo_prefix，未匹配的用同州中位数补，并打 is_geo_imputed 标记
    """
    section("步骤 6 / 7　客户维表聚合（customer_unique_id 一人一行）")
    rows_raw = len(customers)

    # ========== 修复：先关联订单表与客户表，拿到 customer_unique_id ==========
    # orders 只有 customer_id，customers 才有 customer_unique_id
    orders_with_uid = orders.merge(
        customers[["customer_id", "customer_unique_id",
                   "customer_zip_code_prefix", "customer_city", "customer_state"]],
        on="customer_id",
        how="left"
    )

    # 首单：排序后每个客户保留第一条（稳定排序，保证可复现）
    orders_sorted = orders_with_uid.sort_values(
        ["order_purchase_timestamp", "order_id"], kind="mergesort"
    )
    first_order = orders_sorted.drop_duplicates(subset=["customer_unique_id"], keep="first")[
        ["customer_unique_id", "customer_id", "order_purchase_timestamp",
         "customer_zip_code_prefix", "customer_city", "customer_state"]
    ].rename(columns={"order_purchase_timestamp": "first_order_ts"})

    cust_geo = first_order.merge(
        geo[["zip_code_prefix", "lat", "lng"]],
        left_on="customer_zip_code_prefix", right_on="zip_code_prefix", how="left",
    ).drop(columns=["zip_code_prefix"])

    # 坐标缺失：用同州中位数填补（少量），并标记，便于论文说明
    matched = int(cust_geo["lat"].notna().sum())
    cust_geo["is_geo_imputed"] = cust_geo["lat"].isna()
    state_median = cust_geo.groupby("customer_state")[["lat", "lng"]].median()
    for col in ["lat", "lng"]:
        fill = cust_geo["customer_state"].map(state_median[col])
        cust_geo[col] = cust_geo[col].fillna(fill)
    # 州级中位数仍缺（极少数）时用全国中位数兜底
    cust_geo["lat"] = cust_geo["lat"].fillna(cust_geo["lat"].median())
    cust_geo["lng"] = cust_geo["lng"].fillna(cust_geo["lng"].median())

    log(f"  客户行数：{len(cust_geo):,}（客户表原始 {rows_raw:,} 行 / {customers['customer_unique_id'].nunique():,} 个唯一客户）")
    log(f"  坐标直接匹配：{matched:,} 条（{matched / len(cust_geo) * 100:.2f}%）")
    log(f"  坐标州中位数补全：{int(cust_geo['is_geo_imputed'].sum()):,} 条（已标记 is_geo_imputed）")

    # 订单数与累计金额（客户维度的属性，不参与 RFM 计算，RFM 在 03_rfm.py 独立实现）
    order_stat = orders_with_uid.groupby("customer_unique_id").agg(
        order_cnt=("order_id", "nunique"),
        last_order_ts=("order_purchase_timestamp", "max"),
    ).reset_index()
    cust_geo = cust_geo.merge(order_stat, on="customer_unique_id", how="left")
    repeat_rate = float((cust_geo["order_cnt"] >= 2).mean() * 100)
    log(f"  复购客户占比（实测）：{repeat_rate:.2f}%　（profiling 给出的上界为 3.48%）")

    cust_geo = cust_geo[[
        "customer_unique_id", "first_order_ts", "last_order_ts", "order_cnt",
        "customer_zip_code_prefix", "customer_city", "customer_state", "lat", "lng", "is_geo_imputed",
    ]].sort_values("customer_unique_id").reset_index(drop=True)

    assert_unique(cust_geo, ["customer_unique_id"], "customers_clean")
    record("customers_clean", rows_raw, len(cust_geo), "按 customer_unique_id 聚合，地理取首单地址", avg_na(customers), avg_na(cust_geo))
    return cust_geo



# ==============================================================================
# 模块 5：订单主表组装（left join，保留主表全部记录）
# ==============================================================================

def build_orders(orders: pd.DataFrame, pay: pd.DataFrame, items: pd.DataFrame,
                 customers: pd.DataFrame, reviews: pd.DataFrame) -> pd.DataFrame:
    """订单主表：一行一订单，左连支付汇总、明细汇总、客户信息、评分。"""
    section("步骤 7 / 7　订单主表组装（left join，保留全部订单）")
    rows_raw = len(orders)

    # 明细聚合到订单级（只用于订单表展示，不影响 items_clean 明细）
    item_agg = items.groupby("order_id", as_index=False).agg(
        item_cnt=("order_item_id", "count"),
        item_value_total=("price", "sum"),
        freight_total=("freight_value", "sum"),
        seller_cnt=("seller_id", "nunique"),
    )

    df = orders.copy()
    df = df.drop_duplicates(subset=["order_id"], keep="first")   # 防重复订单
    df = df.merge(pay.drop(columns=["is_payment_outlier"]), on="order_id", how="left")
    df = df.merge(item_agg, on="order_id", how="left")
    df = df.merge(
        customers[["customer_id", "customer_unique_id", "customer_zip_code_prefix", "customer_city", "customer_state"]],
        on="customer_id", how="left",
    )
    df = df.merge(reviews[["order_id", "review_id", "review_score"]], on="order_id", how="left")

    # 无匹配项：计数类补 0，分类补 unknown，并保留布尔标记便于论文说明覆盖度
    df["has_payment"] = df["payment_total"].notna()
    df["has_item"] = df["item_cnt"].notna()
    df["has_review"] = df["review_score"].notna()

    for col in ["payment_total", "item_value_total", "freight_total", "payment_installments_mean"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0).astype(float)
    for col in ["payment_record_cnt", "payment_type_cnt", "item_cnt", "seller_cnt"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)
    df["payment_type_main"] = df["payment_type_main"].fillna(UNKNOWN)
    df["customer_unique_id"] = df["customer_unique_id"].fillna(UNKNOWN)
    df["customer_state"] = df["customer_state"].fillna(UNKNOWN)
    df["customer_city"] = df["customer_city"].fillna(UNKNOWN)
    df["customer_zip_code_prefix"] = df["customer_zip_code_prefix"].fillna(UNKNOWN)

    # 时间派生 + 履约指标
    df = add_time_parts(df, "order_purchase_timestamp", prefix="purchase")
    df["delivery_days"] = (df["order_delivered_customer_date"] - df["order_purchase_timestamp"]).dt.days
    # 是否延迟送达：仅在"已送达且承诺日期非空"时可判定，其余记 NA（不武断判为 False）
    df["is_late"] = pd.Series(pd.NA, index=df.index, dtype="boolean")
    late_mask = df["order_delivered_customer_date"].notna() & df["order_estimated_delivery_date"].notna()
    df.loc[late_mask, "is_late"] = (
        df.loc[late_mask, "order_delivered_customer_date"] > df.loc[late_mask, "order_estimated_delivery_date"]
    ).astype("boolean")

    # 异常标记挂在订单级（金额 p99，已在 pay 中算过，这里按订单重算以覆盖全量订单）
    info = add_p99_flag(df, "payment_total", "is_payment_outlier")
    df["is_high_freight"] = df["freight_total"] > df["freight_total"].quantile(P99_Q)

    log(f"  订单行数：{len(df):,}（原始 {rows_raw:,}）")
    log(f"  无支付记录：{int((~df['has_payment']).sum()):,} 条　无明细：{int((~df['has_item']).sum()):,} 条　无评价：{int((~df['has_review']).sum()):,} 条")
    log(f"  履约类日期缺失（不填充）：送达 {int(df['order_delivered_customer_date'].isna().sum()):,} 条，"
        f"交承运商 {int(df['order_delivered_carrier_date'].isna().sum()):,} 条，"
        f"审批 {int(df['order_approved_at'].isna().sum()):,} 条")
    log(f"  is_payment_outlier：{info['n']:,} 条（P99 = {info['threshold']:.2f}）")

    record("orders_clean(全量)", rows_raw, len(df), "左连支付/明细/客户/评价，无匹配项标记", avg_na(orders), avg_na(df))
    return df


# ==============================================================================
# 模块 6：主分析集过滤
# ==============================================================================

def filter_main(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    主分析集：状态 delivered+shipped，时间 2017-01-01 ~ 2018-08-31。
    全状态表单独保留（供漏斗分析），不做时间过滤，仅保留全部状态。
    """
    section("主分析集过滤")
    n_all = len(df)

    status_mask = df["order_status"].isin(MAIN_STATUS)
    time_mask = df["order_purchase_timestamp"].between(ANALYSIS_START, ANALYSIS_END)
    main = df[status_mask & time_mask].copy()

    log(f"  全量订单：{n_all:,}")
    log(f"  状态过滤（{'/'.join(MAIN_STATUS)}）：剔除 {int((~status_mask).sum()):,} 条 → {int(status_mask.sum()):,}")
    log(f"  时间窗过滤（{ANALYSIS_START} ~ {ANALYSIS_END}）：再剔除 {int((status_mask & ~time_mask).sum()):,} 条")
    log(f"  主分析集：{len(main):,} 条（占全量 {len(main) / n_all * 100:.2f}%）")

    # 不纳入核心分析的时间段说明
    early = int(((df["order_purchase_timestamp"] < ANALYSIS_START) & status_mask).sum())
    late = int(((df["order_purchase_timestamp"] > ANALYSIS_END) & status_mask).sum())
    log(f"  剔除原因：2016 年及以前 {early:,} 条（平台早期订单极稀疏）；"
        f"2018-09 以后 {late:,} 条（数据截断、月份不完整）")

    if len(main) < 500:
        raise ValueError(f"主分析集仅 {len(main)} 条，低于硬性要求 500 条，请检查过滤条件")
    log(f"  [校验] 主分析集 ≥500 条 ✓（{len(main):,} 条）")

    record("orders_clean(主分析集)", n_all, len(main), "delivered+shipped 且 2017-01~2018-08", None, None)
    return main, df


# ==============================================================================
# 模块 7：导出与汇总
# ==============================================================================

def export(main: pd.DataFrame, all_status: pd.DataFrame, items: pd.DataFrame,
           customers: pd.DataFrame, pay: pd.DataFrame, reviews: pd.DataFrame,
           geo: pd.DataFrame) -> None:
    """统一导出 7 张 clean 表 + 1 张汇总表。"""
    section("导出结果")

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    TABLE_DIR.mkdir(parents=True, exist_ok=True)

    # 主分析集列顺序（删除仅用于中间计算的冗余列）
    main_cols = [
        "order_id", "customer_id", "customer_unique_id",
        "order_status", "order_purchase_timestamp", "order_approved_at",
        "order_delivered_carrier_date", "order_delivered_customer_date", "order_estimated_delivery_date",
        "payment_total", "payment_type_cnt", "payment_type_main", "payment_installments_mean", "payment_record_cnt",
        "item_cnt", "item_value_total", "freight_total", "seller_cnt",
        "customer_state", "customer_city", "customer_zip_code_prefix",
        "review_score", "review_id",
        "purchase_year", "purchase_quarter", "purchase_month", "purchase_ym", "purchase_weekday", "purchase_weekday_name",
        "delivery_days", "is_late", "is_payment_outlier", "is_high_freight",
        "has_payment", "has_item", "has_review",
    ]
    main_out = main[[c for c in main_cols if c in main.columns]]

    datasets = {
        "orders_clean.csv": main_out,
        "orders_all_status.csv": all_status[[c for c in main_cols if c in all_status.columns]],
        "items_clean.csv": items,
        "customers_clean.csv": customers,
        "payments_order.csv": pay,
        "reviews_order.csv": reviews,
        "geo_prefix.csv": geo,
    }

    for name, df in datasets.items():
        path = CLEAN_DIR / name
        df.to_csv(path, index=False, encoding=CSV_ENCODING)
        log(f"  {name:<26} {len(df):>9,} 行  {df.shape[1]:>2} 列  →  {path}")

    # 主键唯一性最终校验
    assert_unique(main_out, ["order_id"], "orders_clean")
    assert_unique(items, ["order_id", "order_item_id"], "items_clean")
    assert_unique(pay, ["order_id"], "payments_order")
    assert_unique(reviews, ["order_id"], "reviews_order")
    assert_unique(geo, ["zip_code_prefix"], "geo_prefix")
    assert_unique(all_status, ["order_id"], "orders_all_status")

    summary = pd.DataFrame(SUMMARY)
    summary_path = TABLE_DIR / "clean_summary.csv"
    summary.to_csv(summary_path, index=False, encoding=CSV_ENCODING)
    log(f"\n  清洗汇总表 → {summary_path}")

    log("\n  汇总预览：")
    for _, row in summary.iterrows():
        before = "—" if pd.isna(row["avg_missing_pct_before"]) else f"{row['avg_missing_pct_before']:.2f}%"
        after = "—" if pd.isna(row["avg_missing_pct_after"]) else f"{row['avg_missing_pct_after']:.2f}%"
        log(f"    {row['table']:<24} {row['rows_clean']:>8,} 行　缺失率 {before} → {after}")


def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"clean_{datetime.now():%Y%m%d_%H%M%S}.log"

    with open(log_path, "w", encoding="utf-8") as log_file:
        with contextlib.redirect_stdout(Tee(sys.stdout, log_file)):
            log("=" * 78)
            log(f"02_clean.py 运行时间：{datetime.now():%Y-%m-%d %H:%M:%S}")
            log(f"工作目录：{Path.cwd()}")
            log(f"主分析窗：{ANALYSIS_START} ~ {ANALYSIS_END}　状态：{'/'.join(MAIN_STATUS)}")
            log("=" * 78)

            data = load_all()
            pay = build_payments(data["orders"], data["payments"])
            items = build_items(data["items"], data["products"], data["trans"], data["orders"])
            reviews = build_reviews(data["reviews"])
            geo = build_geo(data["geo"])
            cust = build_customers(data["orders"], data["customers"], geo)
            orders_full = build_orders(data["orders"], pay, items, data["customers"], reviews)
            main_df, all_status = filter_main(orders_full)

            export(main_df, all_status, items, cust, pay, reviews, geo)

            section("完成")
            log(f"  日志：{log_path}")
            log("  下一步：核对 outputs/tables/clean_summary.csv 与各表行数，再进入 03_rfm.py")

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
