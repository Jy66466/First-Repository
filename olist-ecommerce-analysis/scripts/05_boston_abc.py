# -*- coding: utf-8 -*-
"""
================================================================================
05_boston_abc.py —— 帕累托/ABC 品类分类 ＋ 波士顿矩阵（份额 × 增速）
================================================================================

功能
    两个模型共用一套「品类 GMV」底座：
      模型一 帕累托/ABC：按品类 GMV 降序累计，划 A/B/C 三级
      模型二 波士顿矩阵：品类份额（X）× 等长窗口同比增速（Y），划四象限

输入
    data/clean/items_clean.csv     订单项明细（112,650 行，**含窗口外订单**）
    data/clean/orders_clean.csv    主分析集订单（97,308 单）

输出
    outputs/tables/abc.csv            category, gmv, share, cum_share, abc_class
    outputs/tables/boston_matrix.csv  category, gmv, share, growth_rate, quadrant
    logs/boston_abc_YYYYmmdd_HHMMSS.log

前置铁律（本脚本最关键的一条）
    items_clean 是**全量明细**（含 2016 年与已取消订单），只有 orders_clean 是主分析集。
    因此必须 items **INNER JOIN** orders_clean ON order_id，
    用主分析集的 97,308 单去"筛"明细；绝不能对 items 全量直接 groupby，
    也不能用 LEFT JOIN（那样窗口外订单的金额会漏进来）。

口径
    品类维度 : product_category_en（英文名；原始缺失已处理为 unknown）
    金额口径 : sum(price)，**不含运费**，币种 **BRL（巴西雷亚尔）**
    份额 X   : 品类 GMV ÷ 全部品类 GMV
    增速 Y   : (2018-01~08 品类 GMV − 2017-01~08 品类 GMV) ÷ 2017-01~08 品类 GMV
               必须等长 8 个月窗口，规避 2018 年数据截断造成的系统性低估
    象限切分 : X 用「品类份额中位数」；Y 用「整体大盘同比增速」（市场基准线）
    ABC 阈值 : 累计占比 ≤80% → A；80%~95% → B；>95% → C（按用户给定口径，字面执行）

两点说明
    1) 极端大额订单（is_price_outlier 标记）**不剔除**：它们是真实的批发/大件交易，
       删除会低估 GMV、扭曲份额。脚本会打印其金额占比供论文说明。
    2) 2017-01~08 无销售的品类（多为 2018 年新上架），增速无法计算，
       其 growth_rate 记空、quadrant 记「未定（基期为 0）」，不强行归入四象限。

运行
    在仓库根目录执行： python scripts/05_boston_abc.py
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

ITEMS_FILE = CLEAN_DIR / "items_clean.csv"
ORDERS_FILE = CLEAN_DIR / "orders_clean.csv"

OUT_ABC = TABLE_DIR / "abc.csv"
OUT_BOSTON = TABLE_DIR / "boston_matrix.csv"
OUT_SENS = TABLE_DIR / "sensitivity_top10.csv"
OUT_META = TABLE_DIR / "boston_meta.csv"

CSV_ENCODING = "utf-8-sig"

# 等长对比窗口（规避 2018 年数据截断）
BASE_WINDOW = ("2017-01", "2017-08")
CURR_WINDOW = ("2018-01", "2018-08")

# ABC 阈值
ABC_A = 0.80
ABC_B = 0.95

# 基准（用于自检）
BASELINE_ORDERS = 97_308

# 最小覆盖率：inner join 后能覆盖主分析集订单的比例下限
MIN_COVERAGE = 0.95

QUADRANTS = ["明星（高份额·高增速）", "金牛（高份额·低增速）",
             "问题（低份额·高增速）", "瘦狗（低份额·低增速）"]
UNASSIGNED = "未定（基期为 0）"

LOGLINES: list[str] = []


# ==============================================================================
# 模块 1：日志工具
# ==============================================================================

class Tee:
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


def brl(x: float) -> str:
    """金额格式化：BRL 千分位，保留 2 位。"""
    return f"R$ {x:,.2f}"


# ==============================================================================
# 模块 2：读取 ＋ inner join（前置铁律）
# ==============================================================================

def load_and_join() -> tuple[pd.DataFrame, pd.DataFrame]:
    section("步骤 1 / 6　读取明细与主表，INNER JOIN 过滤窗口外订单")

    for path in (ITEMS_FILE, ORDERS_FILE):
        if not path.exists():
            raise FileNotFoundError(f"缺少 {path}，请先运行 02_clean.py")

    items = pd.read_csv(ITEMS_FILE, encoding=CSV_ENCODING, low_memory=False)
    orders = pd.read_csv(ORDERS_FILE, encoding=CSV_ENCODING, low_memory=False,
                         usecols=lambda c: c in {"order_id", "has_item"})
    items.columns = [str(c).replace("\ufeff", "").strip() for c in items.columns]
    orders.columns = [str(c).replace("\ufeff", "").strip() for c in orders.columns]

    # 基础类型
    items["price"] = pd.to_numeric(items["price"], errors="coerce").astype(float)
    items["product_category_en"] = items["product_category_en"].fillna("unknown").astype("string")
    items["order_purchase_timestamp"] = pd.to_datetime(items["order_purchase_timestamp"], errors="coerce")

    if items["order_purchase_timestamp"].isna().any():
        raise ValueError(f"明细中有 {int(items['order_purchase_timestamp'].isna().sum())} 行下单时间无法解析")

    # 用时间戳重算年月，避免依赖上游字符串格式
    items["ym"] = items["order_purchase_timestamp"].dt.strftime("%Y-%m")

    # 明细主键唯一性
    dup = int(items.duplicated(subset=["order_id", "order_item_id"]).sum())
    if dup:
        raise ValueError(f"明细主键 (order_id, order_item_id) 有 {dup} 条重复")

    log(f"  明细全量：{len(items):,} 行　订单数 {items['order_id'].nunique():,}　时间 {items['ym'].min()} ~ {items['ym'].max()}")
    log(f"  订单主表：{len(orders):,} 单（主分析集）")

    # ===== 铁律：INNER JOIN，用主分析集筛明细 =====
    joined = items.merge(orders[["order_id"]], on="order_id", how="inner")

    n_main = int(orders["order_id"].nunique())
    n_join = int(joined["order_id"].nunique())
    coverage = n_join / n_main

    log(f"  INNER JOIN 后：{len(joined):,} 行　覆盖订单 {n_join:,} 单")
    log(f"  覆盖率：{coverage * 100:.2f}%（主分析集 {n_main:,} 单）")
    log(f"  主分析集中无明细的订单：{n_main - n_join:,} 单"
        f"（这些订单无商品行，无法参与品类分析，属数据固有缺口，不做填补）")

    if n_join > n_main:
        raise AssertionError(f"inner join 后订单数 {n_join:,} 超过主表 {n_main:,}，关联逻辑有误")
    if coverage < MIN_COVERAGE:
        raise AssertionError(f"覆盖率仅 {coverage * 100:.2f}%，低于 {MIN_COVERAGE * 100:.0f}%，请检查是否误用全量明细")

    # 与订单表的 has_item 标记交叉校验（双向验证，防口径漂移）
    if "has_item" in orders.columns:
        has_item = orders["has_item"]
        if has_item.dtype != bool:
            has_item = has_item.astype(str).str.lower().isin(["true", "1", "1.0"])
        n_no_item = int((~has_item).sum())
        if n_no_item != n_main - n_join:
            raise AssertionError(
                f"has_item 标记的无明细订单数 {n_no_item:,} ≠ 实际差集 {n_main - n_join:,}，两处口径不一致"
            )
        log(f"  [校验] has_item 标记与 join 差集一致 ✓（{n_no_item:,} 单）")

    # 金额合法性
    if (joined["price"] < 0).any():
        raise ValueError("存在负的商品金额，请回到清洗阶段排查")
    if (joined["product_category_en"] == "unknown").any():
        unk_share = joined.loc[joined["product_category_en"] == "unknown", "price"].sum() / joined["price"].sum()
        log(f"  品类 unknown 行数：{int((joined['product_category_en'] == 'unknown').sum()):,}，"
            f"金额占比 {unk_share * 100:.2f}%（保留，不剔除，避免品类 GMV 合计对不上总额）")

    # 异常单价影响（只报告，不剔除）
    if "is_price_outlier" in joined.columns:
        flag = joined["is_price_outlier"]
        if flag.dtype != bool:
            flag = flag.astype(str).str.lower().isin(["true", "1", "1.0"])
        if flag.any():
            out_share = joined.loc[flag, "price"].sum() / joined["price"].sum()
            log(f"  异常单价行：{int(flag.sum()):,} 行（{flag.mean() * 100:.2f}%），"
                f"贡献金额 {out_share * 100:.2f}%——按要求保留，不剔除")

    total_gmv = float(joined["price"].sum())
    log(f"  品类分析总 GMV：{brl(total_gmv)}")
    return items, joined


# ==============================================================================
# 模块 3：帕累托 / ABC
# ==============================================================================

def build_abc(joined: pd.DataFrame) -> tuple[pd.DataFrame, float]:
    section("步骤 2 / 6　帕累托 / ABC 品类分类")

    total = float(joined["price"].sum())
    abc = (joined.groupby("product_category_en", observed=True)["price"]
                 .sum().reset_index()
                 .rename(columns={"product_category_en": "category", "price": "gmv"}))
    abc = abc.sort_values("gmv", ascending=False).reset_index(drop=True)

    abc["share"] = abc["gmv"] / total
    abc["cum_share"] = abc["share"].cumsum()

    # 字面执行用户口径：累计占比 ≤80% 记 A，≤95% 记 B，其余 C
    # 注：跨越阈值的那一个品类会归入下一档（如从 78% 直接跳到 88% 的品类记为 B）
    abc["abc_class"] = np.select(
        [abc["cum_share"] <= ABC_A, abc["cum_share"] <= ABC_B],
        ["A", "B"],
        default="C",
    )

    n_cat = len(abc)
    log(f"  品类数：{n_cat}")
    log(f"  第一品类：{abc.iloc[0]['category']}　{brl(abc.iloc[0]['gmv'])}"
        f"（{abc.iloc[0]['share'] * 100:.2f}%）")

    log("")
    log(f"  {'等级':<6}{'品类数':>7}{'品类占比':>10}{'GMV':>18}{'GMV占比':>10}{'累计占比':>10}")
    log("  " + "-" * 62)
    for cls in ["A", "B", "C"]:
        sub = abc[abc["abc_class"] == cls]
        if sub.empty:
            log(f"  {cls:<6}{0:>7}{0.0:>9.2f}%{'R$ 0.00':>18}{0.0:>9.2f}%")
            continue
        log(f"  {cls:<6}{len(sub):>7}{len(sub) / n_cat * 100:>9.2f}%"
            f"{brl(sub['gmv'].sum()):>18}{sub['gmv'].sum() / total * 100:>9.2f}%"
            f"{sub['cum_share'].max() * 100:>9.2f}%")

    # 帕累托经验值对照（用于论文"是否服从 80/20"的论述）
    for pct in [0.5, 0.8]:
        k = int((abc["cum_share"] < pct).sum()) + 1
        k = min(k, n_cat)
        log(f"  贡献前 {pct * 100:.0f}% GMV 的品类数：{k} 个（占品类 {k / n_cat * 100:.1f}%）")

    return abc, total


# ==============================================================================
# 模块 4：波士顿矩阵
# ==============================================================================

def build_boston(joined: pd.DataFrame, abc: pd.DataFrame, total: float) -> tuple[pd.DataFrame, dict]:
    section("步骤 3 / 6　波士顿矩阵（份额 × 等长窗口增速）")

    # 两个等长窗口的品类 GMV
    base = joined[joined["ym"].between(*BASE_WINDOW)].groupby("product_category_en", observed=True)["price"].sum()
    curr = joined[joined["ym"].between(*CURR_WINDOW)].groupby("product_category_en", observed=True)["price"].sum()

    b = abc[["category", "gmv", "share"]].copy()
    b["gmv_base"] = b["category"].map(base).fillna(0.0)     # 2017-01~08
    b["gmv_curr"] = b["category"].map(curr).fillna(0.0)     # 2018-01~08

    # 增速：基期为 0 时记 NaN（避免除零），后续单独标注
    b["growth_rate"] = np.where(
        b["gmv_base"] > 0,
        (b["gmv_curr"] - b["gmv_base"]) / b["gmv_base"],
        np.nan,
    )

    # 市场基准线：整体大盘的同比增速（同一组等长窗口）
    total_base = float(joined.loc[joined["ym"].between(*BASE_WINDOW), "price"].sum())
    total_curr = float(joined.loc[joined["ym"].between(*CURR_WINDOW), "price"].sum())
    overall_growth = (total_curr - total_base) / total_base

    # X 轴切分线：品类份额中位数
    x_line = float(b["share"].median())

    log(f"  基期 {BASE_WINDOW[0]}~{BASE_WINDOW[1]} 大盘 GMV：{brl(total_base)}")
    log(f"  当期 {CURR_WINDOW[0]}~{CURR_WINDOW[1]} 大盘 GMV：{brl(total_curr)}")
    log(f"  市场基准线（整体同比增速）：{overall_growth * 100:.2f}%")
    log(f"  X 轴切分线（品类份额中位数）：{x_line * 100:.4f}%")

    # 四象限：份额高=严格大于中位数；增速高=严格大于大盘增速
    def classify(row: pd.Series) -> str:
        if pd.isna(row["growth_rate"]):
            return UNASSIGNED
        high_share = row["share"] > x_line
        high_growth = row["growth_rate"] > overall_growth
        if high_share and high_growth:
            return QUADRANTS[0]
        if high_share and not high_growth:
            return QUADRANTS[1]
        if (not high_share) and high_growth:
            return QUADRANTS[2]
        return QUADRANTS[3]

    b["quadrant"] = b.apply(classify, axis=1)

    n_unassigned = int((b["quadrant"] == UNASSIGNED).sum())
    log(f"  基期为 0 无法计算增速的品类：{n_unassigned} 个（记「{UNASSIGNED}」，不强行归象限）")

    log("")
    log(f"  {'象限':<18}{'品类数':>7}{'GMV':>18}{'GMV占比':>10}")
    log("  " + "-" * 55)
    for q in QUADRANTS + [UNASSIGNED]:
        sub = b[b["quadrant"] == q]
        log(f"  {q:<18}{len(sub):>7}{brl(sub['gmv'].sum()):>18}{sub['gmv'].sum() / total * 100:>9.2f}%")

    # 各象限代表品类（按 GMV 排序取前 3）
    log("")
    log("  各象限代表品类（按 GMV 降序，前 3）：")
    for q in QUADRANTS + [UNASSIGNED]:
        sub = b[b["quadrant"] == q].sort_values("gmv", ascending=False).head(3)
        if sub.empty:
            log(f"    {q}：无")
            continue
        names = "；".join([f"{r['category']}（{r['share'] * 100:.1f}%，"
                           f"{'—' if pd.isna(r['growth_rate']) else f'{r.growth_rate * 100:+.1f}%'}）"
                           for _, r in sub.iterrows()])
        log(f"    {q}：{names}")

    meta = {
        "overall_growth": overall_growth,
        "x_line": x_line,
        "total_gmv": total,
        "total_base": total_base,
        "total_curr": total_curr,
    }
    return b, meta


# ==============================================================================
# 模块 5：导出
# ==============================================================================

def export(abc: pd.DataFrame, boston: pd.DataFrame) -> None:
    section("步骤 4 / 7　导出")

    TABLE_DIR.mkdir(parents=True, exist_ok=True)

    abc_out = abc[["category", "gmv", "share", "cum_share", "abc_class"]].copy()
    abc_out["gmv"] = abc_out["gmv"].round(2)
    abc_out["share"] = abc_out["share"].round(6)
    abc_out["cum_share"] = abc_out["cum_share"].round(6)
    abc_out.to_csv(OUT_ABC, index=False, encoding=CSV_ENCODING)
    log(f"  ABC 分类表 → {OUT_ABC}（{len(abc_out)} 行 × {abc_out.shape[1]} 列）")

    boston_out = boston[["category", "gmv", "share", "growth_rate", "quadrant"]].copy()
    boston_out["gmv"] = boston_out["gmv"].round(2)
    boston_out["share"] = boston_out["share"].round(6)
    boston_out["growth_rate"] = boston_out["growth_rate"].round(4)
    boston_out.to_csv(OUT_BOSTON, index=False, encoding=CSV_ENCODING)
    log(f"  波士顿矩阵 → {OUT_BOSTON}（{len(boston_out)} 行 × {boston_out.shape[1]} 列）")

    # 回读校验：空增速不能被写成 0
    check = pd.read_csv(OUT_BOSTON, encoding=CSV_ENCODING)
    n_blank = int(check["growth_rate"].isna().sum())
    if n_blank != int(boston["growth_rate"].isna().sum()):
        raise AssertionError(f"回读校验失败：空增速 {n_blank} 个与预期不符（可能被写成 0）")
    log(f"  [校验] 空增速保持为空 ✓（{n_blank} 个）")


def export_meta(meta: dict) -> None:
    """导出波士顿矩阵的象限基准线，供 07_visuals.py 直接画参考线，避免下游重算口径。"""
    out = pd.DataFrame({
        "metric": ["overall_growth", "x_line_median_share", "total_gmv", "total_base", "total_curr"],
        "value": [float(meta["overall_growth"]), float(meta["x_line"]),
                  float(meta["total_gmv"]), float(meta["total_base"]), float(meta["total_curr"])],
    })
    out.to_csv(OUT_META, index=False, encoding=CSV_ENCODING)
    log(f"  象限基准 → {OUT_META}（大盘增速 {meta['overall_growth'] * 100:.2f}%，"
        f"份额中位数 {meta['x_line'] * 100:.4f}%）")


# ==============================================================================
# 模块 6：自检
# ==============================================================================

def self_check(abc: pd.DataFrame, boston: pd.DataFrame, joined: pd.DataFrame) -> None:
    section("步骤 5 / 7　自检")

    # 1) 两表同源、GMV 一致
    gmv_abc = float(abc["gmv"].sum())
    gmv_bos = float(boston["gmv"].sum())
    gmv_src = float(joined["price"].sum())
    if abs(gmv_abc - gmv_bos) > 0.01 or abs(gmv_abc - gmv_src) > 0.01:
        raise AssertionError(f"GMV 不一致：abc {gmv_abc:.2f} / boston {gmv_bos:.2f} / 明细 {gmv_src:.2f}")
    log(f"  [1/5] 两模型 GMV 同源一致 ✓（{brl(gmv_abc)}）")

    # 2) 累计占比收敛到 1
    last_cum = float(abc["cum_share"].iloc[-1])
    if abs(last_cum - 1.0) > 1e-6:
        raise AssertionError(f"累计占比末位为 {last_cum:.8f}，应为 1")
    log(f"  [2/5] 累计占比末位 = {last_cum:.6f} ✓")

    # 3) 品类唯一、ABC 三档齐全且合计等于品类数
    if abc["category"].duplicated().any():
        raise AssertionError("ABC 表存在重复品类")
    n_sum = int(abc["abc_class"].value_counts().sum())
    if n_sum != len(abc):
        raise AssertionError(f"ABC 三档合计 {n_sum} ≠ 品类数 {len(abc)}")
    log(f"  [3/5] 品类唯一 ✓　三档合计 = {n_sum} ✓")

    # 4) 份额合计为 1
    if abs(float(abc["share"].sum()) - 1.0) > 1e-6:
        raise AssertionError("份额合计不为 1")
    log("  [4/5] 品类份额合计 = 1.000000 ✓")

    # 5) 四象限覆盖检查（除未定外，全部有归属）
    known = set(QUADRANTS) | {UNASSIGNED}
    outside = set(boston["quadrant"]) - known
    if outside:
        raise AssertionError(f"出现未定义象限：{outside}")
    log(f"  [5/5] 象限标签合法 ✓（四象限 + 未定）")

    # 提示：unknown 品类在波士顿图中的影响
    unk = boston[boston["category"] == "unknown"]
    if not unk.empty:
        log(f"  提示：unknown 品类份额 {float(unk['share'].iloc[0]) * 100:.2f}%，"
            f"象限「{unk['quadrant'].iloc[0]}」；论文中可单列说明，不建议混入品类排名解读。")


# ==============================================================================
# 模块 7：终端要点
# ==============================================================================

def sensitivity_check(joined: pd.DataFrame, abc: pd.DataFrame, total: float) -> None:
    """
    敏感性检验：剔除 is_price_outlier 的明细行后，品类 GMV 排名是否发生实质变化。

    动机：异常单价行只占 7% 左右的行数，却贡献了三成以上 GMV，
         若剔除后 Top10 大幅洗牌，说明"品类格局"结论不稳健；
         若 Top10 几乎不变，则核心业务结论可以放心写进论文。
    """
    section("步骤 6 / 7　敏感性检验（剔除异常单价行后重排品类）")

    flag = joined["is_price_outlier"]
    if flag.dtype != bool:
        flag = flag.astype(str).str.lower().isin(["true", "1", "1.0"])

    n_rows, n_out = len(joined), int(flag.sum())
    amt_out = float(joined.loc[flag, "price"].sum())
    log(f"  剔除前：{n_rows:,} 行，GMV {brl(total)}")
    log(f"  异常行：{n_out:,} 行（{n_out / n_rows * 100:.2f}%），金额 {brl(amt_out)}（{amt_out / total * 100:.2f}%）")
    log(f"  剔除后：{n_rows - n_out:,} 行，GMV {brl(total - amt_out)}")

    # 剔除后重新聚合
    gmv_ex = (joined.loc[~flag].groupby("product_category_en", observed=True)["price"].sum())
    b = abc[["category", "gmv"]].copy()
    b["gmv_ex"] = b["category"].map(gmv_ex).fillna(0.0)

    b["rank_full"] = b["gmv"].rank(ascending=False, method="min").astype(int)
    b["rank_ex"] = b["gmv_ex"].rank(ascending=False, method="min").astype(int)
    b["d_rank"] = b["rank_full"] - b["rank_ex"]

    top_full = b.nsmallest(10, "rank_full")["category"].tolist()
    top_ex = b.nsmallest(10, "rank_ex")["category"].tolist()
    set_full, set_ex = set(top_full), set(top_ex)
    entered = sorted(set_ex - set_full)
    dropped = sorted(set_full - set_ex)

    # 斯皮尔曼秩相关：对秩做皮尔逊相关（等价，且不依赖 scipy）
    rho = float(b[["rank_full", "rank_ex"]].corr(method="pearson").iloc[0, 1])

    log("")
    log("  Top10 对比：")
    log(f"    {'名次':<6}{'全量':<28}{'剔除异常后':<28}{'变动'}")
    log("    " + "-" * 72)
    for i in range(10):
        cat_f = top_full[i] if i < len(top_full) else "—"
        cat_e = top_ex[i] if i < len(top_ex) else "—"
        mark = "" if cat_f == cat_e else "←"
        log(f"    {i + 1:<6}{cat_f:<28}{cat_e:<28}{mark}")

    log("")
    log(f"  Top10 集合是否一致：{'是' if not entered and not dropped else '否'}")
    if dropped:
        log(f"    跌出 Top10：{', '.join(dropped)}")
    if entered:
        log(f"    新进 Top10：{', '.join(entered)}")
    log(f"  斯皮尔曼秩相关（72 个品类的整体排名稳定性）：{rho:.4f}")

    moved = b[b["d_rank"] != 0].sort_values("d_rank", key=lambda x: x.abs(), ascending=False)
    if moved.empty:
        log("  所有品类名次完全不变")
    else:
        log(f"  名次发生变动的品类：{len(moved)} 个，变动最大的前 3：")
        for _, r in moved.head(3).iterrows():
            log(f"    {r['category']:<32} 第 {r['rank_full']:>2} 名 → 第 {r['rank_ex']:>2} 名"
                f"（{int(r['d_rank']):+d}）")

    # 结论判定
    stable = (not entered and not dropped) and rho >= 0.9
    log("")
    if stable:
        log("  [结论] Top10 名单未变、整体秩相关 ≥0.9 —— 异常大单没有动摇品类格局，")
        log("         核心业务结论（A 类品类贡献约八成 GMV、明星/金牛名单）稳健，可作为论文主结论。")
    else:
        log("  [结论] 剔除异常后 Top10 名单发生变化，品类排名对极端大单敏感。")
        log(f"         但要注意：这「不等于应当剔除」——异常行虽只占 {n_out / n_rows * 100:.2f}%，")
        log(f"         却承载 {amt_out / total * 100:.2f}% 的 GMV，它们是真实的批发/大件交易，")
        log("         剔除等于丢掉三成业务量，会让规模判断失真。")
        log("         正确做法是双口径报告：主结论用全量口径，敏感性结果作为适用边界；")
        log("         并对名次大幅下滑的品类（多为单笔大单驱动）单独提示经营依赖风险。")

    # 导出对比表（供画图与附录引用）
    out = b[b["category"].isin(set_full | set_ex)].copy()
    out["in_top10_full"] = out["category"].isin(set_full)
    out["in_top10_ex"] = out["category"].isin(set_ex)
    out = out.sort_values("rank_full")[
        ["category", "gmv", "gmv_ex", "rank_full", "rank_ex", "d_rank", "in_top10_full", "in_top10_ex"]
    ]
    out["gmv"] = out["gmv"].round(2)
    out["gmv_ex"] = out["gmv_ex"].round(2)
    out.to_csv(OUT_SENS, index=False, encoding=CSV_ENCODING)
    log(f"  对比表 → {OUT_SENS}（{len(out)} 行）")


def print_highlights(abc: pd.DataFrame, boston: pd.DataFrame, total: float, overall_growth: float) -> None:
    section("步骤 7 / 7　要点小结")

    a = abc[abc["abc_class"] == "A"]
    log(f"  A 类 {len(a)} 个品类（占品类 {len(a) / len(abc) * 100:.1f}%），"
        f"贡献 {a['gmv'].sum() / total * 100:.2f}% 的 GMV——这是选品与资源投放的主战场。")

    star = boston[boston["quadrant"] == QUADRANTS[0]]
    log(f"  明星品类 {len(star)} 个（GMV 占比 {star['gmv'].sum() / total * 100:.2f}%）：加投入、扩库存。")

    cow = boston[boston["quadrant"] == QUADRANTS[1]]
    log(f"  金牛品类 {len(cow)} 个（GMV 占比 {cow['gmv'].sum() / total * 100:.2f}%）：维持、要利润。")
    if len(cow):
        cow_pos = cow[cow["growth_rate"] > 0]
        log(f"    [防误读] 金牛的「低增速」是「相对大盘 {overall_growth * 100:+.1f}%」而言，不是负增长：")
        log(f"             其中 {len(cow_pos)}/{len(cow)} 个品类仍为正增长"
            f"（最高 {cow_pos['growth_rate'].max() * 100:+.1f}%）。论文中不可写成「增长乏力/下滑」。")

    log("")
    tiny = boston[(boston["share"] < 0.002) & boston["growth_rate"].notna()]
    if len(tiny):
        log(f"  [防误读] {len(tiny)} 个份额 <0.2% 的小品类，增速受基数影响剧烈"
            f"（最高 {tiny['growth_rate'].max() * 100:+.0f}%），解读时只看方向、不看幅度。")

    log("  [口径提示] 本脚本金额为商品金额（price），不含运费；RFM 的 M 为支付金额（含运费），")
    log("             两处数字不可直接相减或互相校验，论文中需分别标注口径。")


# ==============================================================================
# 主流程
# ==============================================================================

def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"boston_abc_{datetime.now():%Y%m%d_%H%M%S}.log"

    with open(log_path, "w", encoding="utf-8") as log_file:
        with contextlib.redirect_stdout(Tee(sys.stdout, log_file)):
            log("=" * 78)
            log(f"05_boston_abc.py 运行时间：{datetime.now():%Y-%m-%d %H:%M:%S}")
            log(f"工作目录：{Path.cwd()}")
            log(f"对比窗口：{BASE_WINDOW[0]}~{BASE_WINDOW[1]} vs {CURR_WINDOW[0]}~{CURR_WINDOW[1]}")
            log("=" * 78)

            _, joined = load_and_join()
            abc, total = build_abc(joined)
            boston, meta = build_boston(joined, abc, total)
            export(abc, boston)
            export_meta(meta)
            self_check(abc, boston, joined)
            sensitivity_check(joined, abc, total)
            print_highlights(abc, boston, total, meta["overall_growth"])

            section("完成")
            log(f"  日志：{log_path}")
            log("  下一步：核对 boston_matrix.csv 的象限分布，再进入 06_forecast.py")

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
