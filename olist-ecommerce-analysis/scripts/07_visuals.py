# -*- coding: utf-8 -*-
"""
================================================================================
07_visuals.py —— 业务模型图（fig12 ~ fig20，共 9 张，全 Python 生成）
================================================================================

功能
    读取 outputs/tables 下五个模型的输出表，一键生成 9 张业务模型图；
    统一字体、配色、DPI、标注风格，可直接进论文与答辩 PPT。

输入（全部来自上游脚本的产出，不重算模型）
    outputs/tables/rfm.csv              fig12 / fig13
    outputs/tables/rfm_summary.csv      fig13
    outputs/tables/cohort_matrix.csv    fig14 / fig15
    outputs/tables/boston_matrix.csv    fig16 / fig17
    outputs/tables/boston_meta.csv      fig16（象限基准线）
    outputs/tables/abc.csv              fig18 / fig19
    outputs/tables/forecast.csv         fig20

输出
    outputs/figures/fig12_rfm_bubble.png
    outputs/figures/fig13_rfm_gmv_bar.png
    outputs/figures/fig14_cohort_heatmap.png
    outputs/figures/fig15_cohort_line.png
    outputs/figures/fig16_boston_bubble.png
    outputs/figures/fig17_boston_bar.png
    outputs/figures/fig18_pareto_line.png
    outputs/figures/fig19_abc_stacked.png
    outputs/figures/fig20_forecast_interval.png
    logs/visuals_YYYYmmdd_HHMMSS.log

规范
    分辨率 150 dpi；中文字体 Microsoft YaHei（缺省回退 SimHei）；
    金额统一 BRL，轴刻度用千分位；配色全篇一致；
    每张图右下角标注口径说明，避免图文对不上。

两点设计说明（与需求略有调整，理由写在代码注释里）
    1) fig13 未使用双 Y 轴：客户数占比与 GMV 占比同为百分比，双轴会制造视觉误导，
       改为同轴分组柱 + 数值标签，对比更准确。
    2) fig14 色标上限设为 1%：第 0 月恒为 100%，若按真实值着色，
       其余 12 列会全部压成浅色；设上限后月龄差异可辨，图中已注明。

运行
    在仓库根目录执行： python scripts/07_visuals.py
    只画某几张：        python scripts/07_visuals.py --only 12 16
================================================================================
"""

from __future__ import annotations

import argparse
import sys
import traceback
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # 无界面后端，服务器/批处理环境也能出图

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import seaborn as sns  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch, Rectangle  # noqa: E402
from matplotlib.ticker import FuncFormatter, PercentFormatter  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# ==============================================================================
# 模块 0：全局配置
# ==============================================================================

TABLE_DIR = Path("outputs/tables")
FIG_DIR = Path("outputs/figures")
LOG_DIR = Path("logs")

CSV_ENCODING = "utf-8-sig"
DPI = 150
RNG_SEED = 42          # 抖动固定种子，保证图可复现

# 商务配色：深蓝为主、暖橙为辅，整体低饱和，投影与打印都稳
C_DARK = "#1f3864"
C_BLUE = "#2e75b6"
C_MID = "#5b9bd5"
C_LIGHT = "#8faadc"
C_ORANGE = "#c55a11"
C_GOLD = "#bf9000"
C_GREEN = "#548235"
C_GREY = "#a6a6a6"

# 8 个客户分群（按业务含义配置，避免同色系混淆）
SEGMENT_COLORS = {
    "重要价值客户": "#1f3864",
    "重要发展客户": "#2e75b6",
    "重要保持客户": "#548235",
    "重要挽留客户": "#c55a11",
    "一般价值客户": "#8faadc",
    "一般发展客户": "#a9d18e",
    "一般保持客户": "#f4b183",
    "一般挽留客户": "#bfbfbf",
}

# 四象限
QUADRANT_COLORS = {
    "明星（高份额·高增速）": "#c00000",
    "金牛（高份额·低增速）": "#bf9000",
    "问题（低份额·高增速）": "#2e75b6",
    "瘦狗（低份额·低增速）": "#a6a6a6",
    "未定（基期为 0）": "#d9d9d9",
}

# ABC 三档
ABC_COLORS = {"A": "#1f3864", "B": "#5b9bd5", "C": "#d6dce5"}

FIGURES: list[tuple[str, int]] = []


# ==============================================================================
# 模块 1：全局样式与通用工具
# ==============================================================================

def setup_style() -> None:
    """统一字体、字号、网格与边框风格。"""
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
        "axes.unicode_minus": False,
        "text.parse_math": False,   # 关闭 $...$ 公式解析，R$ 才能正常显示      # 负号正常显示
        "figure.dpi": 110,
        "savefig.dpi": DPI,
        "axes.titlesize": 16,
        "axes.titleweight": "bold",
        "axes.titlepad": 34,
        "axes.labelsize": 11,
        "axes.labelcolor": "#333333",
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "legend.fontsize": 9,
        "legend.frameon": True,
        "legend.framealpha": 0.92,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.edgecolor": "#999999",
        "grid.alpha": 0.25,
        "grid.linestyle": "--",
        "grid.color": "#999999",
    })


def load_table(name: str) -> pd.DataFrame:
    """读取结果表，剥离可能的 BOM，缺文件直接报错（不静默跳过）。"""
    path = TABLE_DIR / name
    if not path.exists():
        raise FileNotFoundError(f"缺少 {path}，请先运行对应模型脚本")
    df = pd.read_csv(path, encoding=CSV_ENCODING)
    df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]
    return df


def load_meta() -> dict:
    """读取波士顿象限基准线。"""
    df = load_table("boston_meta.csv")
    return dict(zip(df["metric"], df["value"].astype(float)))


def thousands(x, _pos=None) -> str:
    """轴刻度千分位（不带货币符号，货币写在轴标题里）。"""
    return f"{x:,.0f}"


def pct(x, _pos=None) -> str:
    """比例转百分比文本。"""
    return f"{x * 100:.1f}%"


def finish(ax, note: str = "", grid_axis: str = "y") -> None:
    """统一收尾：网格在下、右上留白。"""
    ax.grid(axis=grid_axis, alpha=0.25, linestyle="--")
    ax.set_axisbelow(True)


def save(fig, filename: str, note: str = "", note_y: float = 0.002) -> None:
    """保存并登记；顺手校验文件确实生成且不是空图。"""
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    if note:
        fig.text(0.005, note_y, note, fontsize=7.5, color="#7f7f7f", ha="left", va="bottom")
    path = FIG_DIR / filename
    fig.savefig(path, dpi=DPI, bbox_inches="tight", facecolor="white", pad_inches=0.28)
    plt.close(fig)

    size = path.stat().st_size if path.exists() else 0
    if size < 20_000:
        raise AssertionError(f"{filename} 生成异常（{size} 字节），请检查是否空图")
    FIGURES.append((filename, size))
    print(f"  [OK] {filename:<32} {size / 1024:7.1f} KB")


# ==============================================================================
# 模块 2：fig12 RFM 气泡散点图
# ==============================================================================

def fig12_rfm_bubble() -> None:
    rfm = load_table("rfm.csv")
    summary = load_table("rfm_summary.csv")
    order = summary.sort_values("GMV总额", ascending=False)["Segment"].tolist()

    # F 因复购率仅 3%，97% 落在 1，直接散点会完全重叠成一横条 —— 加固定种子抖动
    rng = np.random.default_rng(RNG_SEED)
    rfm["F_plot"] = rfm["F"] + rng.normal(0, 0.09, len(rfm))

    # 气泡面积按 GMV 的平方根缩放（面积∝M），并对 99 分位封顶，避免个别大单吃掉整张图
    cap = float(rfm["M"].quantile(0.99))
    size = np.clip(np.sqrt(rfm["M"].clip(upper=cap) / cap) * 150, 4, 160)

    # 右侧留一条窄栏放 F 分布：散点里 97% 的点挤在 F=1，光看散点说不清这个比例
    fig, (ax, ax_panel) = plt.subplots(
        1, 2, figsize=(13.4, 6.8),
        gridspec_kw={"width_ratios": [3.6, 1.0]},
    )
    fig.subplots_adjust(wspace=0.24)

    handles = []
    for seg in order:
        mask = rfm["Segment"] == seg
        ax.scatter(rfm.loc[mask, "R"], rfm.loc[mask, "F_plot"],
                   s=size[mask], c=SEGMENT_COLORS.get(seg, C_GREY),
                   alpha=0.32, linewidths=0, label=seg, rasterized=True)
        handles.append(Line2D([0], [0], marker="o", color="none",
                              markerfacecolor=SEGMENT_COLORS.get(seg, C_GREY),
                              markersize=8, label=f"{seg}（{int(mask.sum()):,} 户）"))

    # 标注两个「高价值但只买一次」的分群：它们在 R 轴上分居两侧、在 F 轴上重叠
    for seg, dy in [("重要发展客户", 1.6), ("重要挽留客户", 2.6)]:
        sub = rfm[rfm["Segment"] == seg]
        if sub.empty:
            continue
        cx, cy = float(sub["R"].median()), 1.0
        ax.annotate(f"{seg}\n{len(sub):,} 户 / GMV 占比 "
                    f"{float(summary.loc[summary['Segment'] == seg, 'GMV占比'].iloc[0]):.1f}%",
                    xy=(cx, cy), xytext=(cx, cy + dy),
                    fontsize=9, color="#333333", ha="center",
                    arrowprops=dict(arrowstyle="->", color="#666666", lw=1.0,
                                    connectionstyle="arc3,rad=0.15"),
                    bbox=dict(boxstyle="round,pad=0.35", fc="white", ec="#cccccc", alpha=0.9))

    ax.set_xlabel("R：距最近一次购买的天数（越小越活跃）")
    ax.set_ylabel("F：购买次数（已加抖动，F=1 占 97%）")
    ax.set_title("RFM 客户价值分布：九成七客户只买过一次", loc="left")
    ax.text(0.0, 1.005, f"气泡大小 = 客户 GMV（封顶 P99 = R$ {cap:,.0f}）　"
                       f"样本：{len(rfm):,} 户 / {len(order)} 个分群",
            transform=ax.transAxes, fontsize=9, color="#666666")
    ax.set_ylim(0.4, max(rfm["F_plot"].max() + 0.5, 4))
    finish(ax, grid_axis="both")
    ax.legend(handles=handles, loc="upper right", ncol=2, fontsize=8, title="分群（客户数）",
              title_fontsize=8.5)

    # F 分布面板：把"九成七只买一次"从形容变成可读的两块数字
    f1 = int((rfm["F"] == 1).sum())
    f2 = int((rfm["F"] >= 2).sum())
    total = len(rfm)
    ax_panel.set_xlim(0, 1)
    ax_panel.set_ylim(0, 1)
    ax_panel.axis("off")
    ax_panel.text(0.02, 1.0, "F 分布", transform=ax_panel.transAxes,
                  ha="left", va="top", fontsize=11, color="#333333", weight="bold")
    ax_panel.text(0.5, 0.66, f"F=1\n{f1:,} 户\n{f1 / total * 100:.2f}%",
                  transform=ax_panel.transAxes,
                  ha="center", va="center", fontsize=14, color=C_DARK, weight="bold")
    ax_panel.text(0.5, 0.28, f"F≥2\n{f2:,} 户\n{f2 / total * 100:.2f}%",
                  transform=ax_panel.transAxes,
                  ha="center", va="center", fontsize=14, color=C_ORANGE, weight="bold")

    save(fig, "fig12_rfm_bubble.png",
         "口径：R 以数据最大下单日 +1 天为快照日；M 为 payment_total 汇总（含运费，BRL）；"
         "F 抖动为固定种子 42 的随机偏移，仅用于可视化，不改变统计值。")


# ==============================================================================
# 模块 3：fig13 客户价值贡献柱状图
# ==============================================================================

def fig13_rfm_gmv_bar() -> None:
    df = load_table("rfm_summary.csv").sort_values("GMV占比", ascending=False).reset_index(drop=True)

    x = np.arange(len(df))
    w = 0.38
    fig, ax = plt.subplots(figsize=(11.5, 6.2))

    b1 = ax.bar(x - w / 2, df["客户数占比"], w, label="客户数占比",
                color=C_LIGHT, edgecolor="white", linewidth=0.8)
    b2 = ax.bar(x + w / 2, df["GMV占比"], w, label="GMV 占比",
                color=C_DARK, edgecolor="white", linewidth=0.8)

    for bars in (b1, b2):
        for rect in bars:
            h = rect.get_height()
            ax.annotate(f"{h:.1f}%", (rect.get_x() + rect.get_width() / 2, h),
                        ha="center", va="bottom", fontsize=8, color="#333333",
                        xytext=(0, 2), textcoords="offset points")

    ax.set_xticks(x)
    ax.set_xticklabels(df["Segment"], rotation=18, ha="right")
    ax.set_ylabel("占比（%）")
    ax.set_ylim(0, max(df["GMV占比"].max(), df["客户数占比"].max()) * 1.22)
    ax.set_title("客户价值贡献：47% 的客户贡献了 75% 的 GMV", loc="left")
    ax.text(0.0, 1.005, "同一纵轴对比两项占比（不采用双 Y 轴，避免视觉误导）；"
                       "按 GMV 占比降序", transform=ax.transAxes, fontsize=9, color="#666666")
    finish(ax)
    ax.legend(loc="upper right")

    save(fig, "fig13_rfm_gmv_bar.png",
         "数据源：rfm_summary.csv；占比基数分别为 94,136 户与 GMV 合计 R$ 15,551,539.96（含运费）。")


# ==============================================================================
# 模块 4：fig14 留存热力图
# ==============================================================================

def fig14_cohort_heatmap() -> None:
    mat = pd.read_csv(TABLE_DIR / "cohort_matrix.csv", encoding=CSV_ENCODING, index_col="cohort_month")
    mat.columns = [str(c).strip() for c in mat.columns]
    mat = mat.apply(pd.to_numeric, errors="coerce")

    fig, ax = plt.subplots(figsize=(11.8, 7.2))
    # 掩膜区（未观测）用浅灰底，避免与"接近 0"的浅蓝格子混淆
    ax.set_facecolor("#d9d9d9")
    # vmax 取 1%：第 0 月恒为 100%，若按真实值着色会把其余列全部压成浅色
    sns.heatmap(mat, mask=mat.isna(), cmap="Blues", vmin=0.0, vmax=0.01,
                linewidths=0.4, linecolor="white",
                cbar_kws={"label": "留存率（色标上限 1%，第 0 月已饱和）", "shrink": 0.82},
                ax=ax)

    # 未观测格加斜线：只靠灰底仍会被读成"接近 0"，斜线是唯一不与色阶混淆的编码
    for i, cohort in enumerate(mat.index):
        for j, month in enumerate(mat.columns):
            if pd.isna(mat.loc[cohort, month]):
                ax.add_patch(Rectangle((j, i), 1, 1, fill=False,
                                       hatch="///", edgecolor="#b7b7b7",
                                       linewidth=0.0, zorder=3))

    cbar = ax.collections[0].colorbar
    cbar.ax.yaxis.set_major_formatter(PercentFormatter(1.0, decimals=2))

    ax.set_xlabel("Month Index（首购后第 n 个月）")
    ax.set_ylabel("Cohort（首购年月）")
    ax.set_title("同期群留存矩阵：第 1 月即断崖，之后长期贴地", loc="left")
    ax.text(0.0, 1.005, "灰色斜线格 = 数据截止 2018-08 尚未观测到（非 0），共 55 个",
            transform=ax.transAxes, fontsize=9, color="#666666")
    ax.tick_params(axis="x", rotation=0)
    ax.tick_params(axis="y", rotation=0)

    save(fig, "fig14_cohort_heatmap.png",
         "数据源：cohort_matrix.csv；留存率 = 该月有订单客户数 ÷ cohort 规模；同月多单只计 1 次。")


# ==============================================================================
# 模块 5：fig15 留存趋势折线图
# ==============================================================================

def fig15_cohort_line() -> None:
    mat = pd.read_csv(TABLE_DIR / "cohort_matrix.csv", encoding=CSV_ENCODING, index_col="cohort_month")
    mat.columns = [str(c).strip() for c in mat.columns]
    mat = mat.apply(pd.to_numeric, errors="coerce")

    # 代表 cohort：首月（最早期）、年中、黑五当月（最大群）、次年初
    picks = [c for c in ["2017-01", "2017-06", "2017-11", "2018-01"] if c in mat.index]
    if not picks:
        raise ValueError("cohort_matrix.csv 中找不到可用的代表 cohort")

    cols = [str(i) for i in range(7)]
    fig, ax = plt.subplots(figsize=(10.6, 6.2))

    colors = [C_DARK, C_BLUE, C_ORANGE, C_GREEN]
    for c, color in zip(picks, colors):
        y = mat.loc[c, cols].astype(float).values * 100
        y = np.where(y <= 0, np.nan, y)   # 0 无法上对数轴，置空
        ax.plot(range(7), y, marker="o", markersize=6, linewidth=2.0,
                color=color, label=f"{c}（{int(y[0]):.0f}% → {y[1]:.2f}%）" if not np.isnan(y[1]) else c)

    ax.set_yscale("log")
    ax.set_ylim(0.05, 160)
    ax.set_xticks(range(7))
    ax.set_xlabel("Month Index（0 = 首购当月）")
    ax.set_ylabel("留存率（%，对数刻度）")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, p: f"{v:g}%"))
    ax.set_title("留存曲线：0 月 100% → 1 月不足 1%，随后进入长尾", loc="left")
    ax.text(0.0, 1.005, "对数刻度：否则 1 月之后的差异在图上完全看不见；第 0 月恒为 100%",
            transform=ax.transAxes, fontsize=9, color="#666666")
    finish(ax, grid_axis="both")
    ax.legend(loc="upper right", title="Cohort（括号内为 0 月→1 月留存）",
              title_fontsize=8.5, framealpha=0.95)

    # 标注 1 月断崖
    ax.annotate("首购后第 1 个月\n平均留存 0.49%",
                xy=(1, 0.49), xytext=(2.2, 6),
                fontsize=9, color="#c55a11",
                arrowprops=dict(arrowstyle="->", color="#c55a11", lw=1.1),
                bbox=dict(boxstyle="round,pad=0.35", fc="white", ec="#f4b183", alpha=0.95))

    save(fig, "fig15_cohort_line.png",
         "数据源：cohort_matrix.csv（2017-01~2018-06，共 18 个队列）；0 值因对数轴无法显示，已置空。")


# ==============================================================================
# 模块 6：fig16 波士顿矩阵四象限气泡图
# ==============================================================================

def fig16_boston_bubble() -> None:
    df = load_table("boston_matrix.csv")
    meta = load_meta()

    x_line = float(meta["x_line_median_share"])
    y_line = float(meta["overall_growth"])

    plot = df.dropna(subset=["growth_rate"]).copy()
    n_nan = len(df) - len(plot)

    # 增速限制在 -50% ~ +300%，超界点吸附到边界并单独标记
    y_lo, y_hi = -0.50, 3.00
    plot["y_plot"] = plot["growth_rate"].clip(lower=y_lo, upper=y_hi)
    plot["clipped"] = (plot["growth_rate"] < y_lo) | (plot["growth_rate"] > y_hi)

    cap = float(plot["gmv"].quantile(0.97))
    plot["size"] = np.clip(np.sqrt(plot["gmv"].clip(upper=cap) / cap) * 520, 30, 900)

    fig, ax = plt.subplots(figsize=(11.6, 7.4))

    for q, color in QUADRANT_COLORS.items():
        sub = plot[(plot["quadrant"] == q) & (~plot["clipped"])]
        if sub.empty:
            continue
        ax.scatter(sub["share"], sub["y_plot"], s=sub["size"], c=color,
                   alpha=0.55, edgecolors="white", linewidths=0.8, label=q, zorder=3)

    # 超界点：用三角标记贴在边界上
    over = plot[plot["clipped"] & (plot["growth_rate"] > y_hi)]
    under = plot[plot["clipped"] & (plot["growth_rate"] < y_lo)]
    if not over.empty:
        ax.scatter(over["share"], over["y_plot"], s=78, marker="^", c=C_ORANGE,
                   edgecolors="white", linewidths=0.8, zorder=4,
                   label=f"增速 > 300%（{len(over)} 个，已截断）")
    if not under.empty:
        ax.scatter(under["share"], under["y_plot"], s=78, marker="v", c=C_GREY,
                   edgecolors="white", linewidths=0.8, zorder=4,
                   label=f"增速 < -50%（{len(under)} 个，已截断）")

    # 基准线
    ax.axvline(x_line, color="#666666", linestyle="--", linewidth=1.2, zorder=2)
    ax.axhline(y_line, color="#666666", linestyle="--", linewidth=1.2, zorder=2)
    ax.text(x_line * 1.06, y_lo * 0.92, f"份额中位数 {x_line * 100:.2f}%",
            fontsize=8.5, color="#555555", ha="left", va="bottom")
    ax.text(1.1e-5, y_line + 0.06,
            f"大盘增速 {y_line * 100:+.1f}%", fontsize=8.5, color="#555555", ha="left")

    # 象限标签（四角）
    ax.text(0.985, 0.97, "明星\n高份额·高增速", transform=ax.transAxes, ha="right", va="top",
            fontsize=11, color="#c00000", weight="bold", alpha=0.85)
    ax.text(0.015, 0.97, "问题\n低份额·高增速", transform=ax.transAxes, ha="left", va="top",
            fontsize=11, color="#2e75b6", weight="bold", alpha=0.85)
    ax.text(0.985, 0.05, "金牛\n高份额·低增速", transform=ax.transAxes, ha="right", va="bottom",
            fontsize=11, color="#bf9000", weight="bold", alpha=0.85)
    ax.text(0.015, 0.05, "瘦狗\n低份额·低增速", transform=ax.transAxes, ha="left", va="bottom",
            fontsize=11, color="#7f7f7f", weight="bold", alpha=0.85)

    # 代表品类文字：每象限取 GMV 前 2
    offsets = {"明星（高份额·高增速）": (6, 10), "金牛（高份额·低增速）": (-6, -16),
               "问题（低份额·高增速）": (10, -18), "瘦狗（低份额·低增速）": (-4, -14)}
    for q in QUADRANT_COLORS:
        sub = plot[plot["quadrant"] == q].nlargest(2, "gmv")
        dx, dy = offsets.get(q, (5, 8))
        for _, r in sub.iterrows():
            ax.annotate(str(r["category"]), xy=(r["share"], r["y_plot"]),
                        xytext=(dx, dy), textcoords="offset points",
                        fontsize=8.2, color="#333333",
                        bbox=dict(boxstyle="round,pad=0.18", fc="white", ec="none", alpha=0.7))

    ax.set_xscale("log")
    ax.set_xlim(float(plot["share"].min()) * 0.45, float(plot["share"].max()) * 2.4)
    ax.set_ylim(y_lo - 0.12, y_hi + 0.35)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, p: f"{v * 100:g}%"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, p: f"{v * 100:.0f}%"))
    ax.set_xlabel("品类份额（对数刻度，%）")
    ax.set_ylabel("同比增速（%，2018-01~08 vs 2017-01~08）")
    ax.set_title("波士顿矩阵：金牛贡献 53% GMV，但“低增速”只是跑输大盘", loc="left")
    ax.text(0.0, 1.005,
            f"72 个品类；气泡大小 = GMV（封顶 P97 = R$ {cap:,.0f}）；"
            f"基期为 0 的 {n_nan} 个品类未入图",
            transform=ax.transAxes, fontsize=9, color="#666666")
    finish(ax, grid_axis="both")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=4,
              fontsize=8.2, frameon=False)

    save(fig, "fig16_boston_bubble.png",
         "数据源：boston_matrix.csv + boston_meta.csv；X 轴切分线 = 份额中位数，"
         "Y 轴切分线 = 大盘同比增速；品类维度为 product_category_en，金额不含运费。")


# ==============================================================================
# 模块 7：fig17 品类象限分布条形图
# ==============================================================================

def fig17_boston_bar() -> None:
    df = load_table("boston_matrix.csv")
    order = [q for q in QUADRANT_COLORS if q in set(df["quadrant"])]
    cnt = df.groupby("quadrant").size().reindex(order).fillna(0)
    gmv = df.groupby("quadrant")["gmv"].sum().reindex(order).fillna(0)
    colors = [QUADRANT_COLORS[q] for q in order]

    fig, axes = plt.subplots(1, 2, figsize=(12.4, 5.8), sharey=True)
    fig.subplots_adjust(top=0.72, wspace=0.18)
    labels = [q.split("（")[0] for q in order]

    ax = axes[0]
    bars = ax.barh(labels, cnt.values, color=colors, alpha=0.9, height=0.62)
    for r, v in zip(bars, cnt.values):
        ax.annotate(f"{int(v)} 个（{v / cnt.sum() * 100:.0f}%）",
                    (r.get_width(), r.get_y() + r.get_height() / 2),
                    xytext=(4, 0), textcoords="offset points", va="center", fontsize=9)
    ax.set_xlabel("品类数量（个）")
    ax.set_title("品类数量分布", loc="left", fontsize=13)
    ax.set_xlim(0, cnt.max() * 1.35)
    finish(ax, grid_axis="x")

    ax = axes[1]
    bars = ax.barh(labels, gmv.values / 1e6, color=colors, alpha=0.9, height=0.62)
    for r, v in zip(bars, gmv.values):
        amt = f"R$ {v / 1e6:.2f}M" if v >= 1e5 else f"R$ {v / 1e3:.1f}K"
        ax.annotate(f"{amt}（{v / gmv.sum() * 100:.1f}%）",
                    (r.get_width(), r.get_y() + r.get_height() / 2),
                    xytext=(4, 0), textcoords="offset points", va="center", fontsize=9)
    ax.set_xlabel("GMV（百万 R$）")
    ax.set_title("GMV 贡献分布", loc="left", fontsize=13)
    ax.set_xlim(0, gmv.max() / 1e6 * 1.42)
    finish(ax, grid_axis="x")

    fig.text(0.012, 0.955, "四象限的两极：明星+金牛 36 个品类拿走 96% 的 GMV",
             ha="left", fontsize=16, weight="bold")
    fig.text(0.012, 0.895, "同为 18 个品类，金牛的 GMV 是明星的 1.2 倍；问题+瘦狗 34 个品类合计不足 4%",
             fontsize=9, color="#666666")
    fig.text(0.012, 0.856,
             "注：另有 2 个基期为 0 的品类（diapers_and_hygiene、flowers）记为未定，未纳入四象限；四象限合计 70 个。",
             fontsize=8.5, color="#666666")

    save(fig, "fig17_boston_bar.png",
         "数据源：boston_matrix.csv；品类 72 个（含 unknown 与 2 个基期为 0 的未定品类）。")


# ==============================================================================
# 模块 8：fig18 帕累托曲线
# ==============================================================================

def fig18_pareto_line() -> None:
    df = load_table("abc.csv").sort_values("gmv", ascending=False).reset_index(drop=True)

    x = np.arange(len(df))
    colors = [ABC_COLORS.get(c, C_GREY) for c in df["abc_class"]]

    fig, ax = plt.subplots(figsize=(13.4, 6.6))
    ax.bar(x, df["gmv"] / 1e6, color=colors, width=0.82, edgecolor="white", linewidth=0.4)

    ax2 = ax.twinx()
    ax2.plot(x, df["cum_share"] * 100, color=C_ORANGE, linewidth=2.2, marker="", zorder=5)
    ax2.set_ylim(0, 105)
    ax2.set_ylabel("累计占比（%）", color=C_ORANGE)
    ax2.tick_params(axis="y", colors=C_ORANGE)
    ax2.spines["right"].set_visible(True)
    ax2.spines["right"].set_color(C_ORANGE)

    # 80% / 95% 参考线
    for yv, label, color in [(80, "80%（A 类阈值）", "#c00000"), (95, "95%（B 类阈值）", "#7f7f7f")]:
        ax2.axhline(yv, color=color, linestyle="--", linewidth=1.1, alpha=0.8)
        ax2.text(len(df) - 0.5, yv + 1.5, label, fontsize=8.5, color=color, ha="right")

    # 只显示 Top20 的品类名，其余留空避免糊成一片
    ticks = list(range(20))
    ax.set_xticks(ticks)
    short = [c if len(c) <= 16 else c[:15] + "…" for c in df.loc[ticks, "category"]]
    ax.set_xticklabels(short, rotation=90, ha="center", va="top", fontsize=6.5)
    ax.axvline(19.5, color="#cccccc", linestyle=":", linewidth=1.0)
    ax.set_xlim(-0.8, len(df) - 0.2)
    ax.set_xlabel("品类（按 GMV 降序，仅标注 Top 20，其余 52 个略）", labelpad=26)
    ax.set_ylabel("GMV（百万 R$）")
    ax.set_title("帕累托：25% 的品类贡献 80% 的 GMV", loc="left")
    ax.text(0.0, 1.005, "柱色 = ABC 分级；折线 = 累计占比；右轴为累计百分比",
            transform=ax.transAxes, fontsize=9, color="#666666")
    finish(ax)
    ax2.grid(False)

    handles = [Patch(facecolor=ABC_COLORS[c], label=f"{c} 类") for c in ["A", "B", "C"]]
    ax.legend(handles=handles, loc="center right")

    save(fig, "fig18_pareto_line.png",
         "数据源：abc.csv；A ≤80%、B 80%~95%、C >95%（累计占比口径）；金额为商品金额，不含运费。",
         note_y=-0.17)


# ==============================================================================
# 模块 9：fig19 ABC 分级贡献堆叠图
# ==============================================================================

def fig19_abc_stacked() -> None:
    df = load_table("abc.csv")
    cnt = df.groupby("abc_class").size().reindex(["A", "B", "C"]).fillna(0)
    gmv = df.groupby("abc_class")["gmv"].sum().reindex(["A", "B", "C"]).fillna(0)

    cnt_share = cnt / cnt.sum() * 100
    gmv_share = gmv / gmv.sum() * 100

    fig, ax = plt.subplots(figsize=(11.2, 4.6))
    rows = ["品类数量占比", "GMV 贡献占比"]
    data = np.vstack([cnt_share.values, gmv_share.values])
    left = np.zeros(2)

    for i, cls in enumerate(["A", "B", "C"]):
        vals = data[:, i]
        ax.barh(rows, vals, left=left, color=ABC_COLORS[cls], height=0.52,
                edgecolor="white", linewidth=1.5, label=f"{cls} 类")
        for j, v in enumerate(vals):
            if v >= 4:   # 太窄的段不标数字，避免压字
                ax.text(left[j] + v / 2, j, f"{v:.1f}%", ha="center", va="center",
                        color="white" if cls == "A" else "#333333", fontsize=10, weight="bold")
        left += vals

    ax.set_xlim(0, 100)
    ax.set_xlabel("占比（%）")
    ax.invert_yaxis()
    ax.set_ylim(1.42, -0.58)
    ax.set_title("ABC 分级：23.6% 的品类撑起 79.7% 的 GMV", loc="left")
    ax.text(0.0, 1.005, "同一套品类，两种口径的份额对比：A 类的“数量少、贡献大”一目了然",
            transform=ax.transAxes, fontsize=9, color="#666666")
    finish(ax, grid_axis="x")
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.20), ncol=3, frameon=False)

    save(fig, "fig19_abc_stacked.png",
         "数据源：abc.csv；品类数 72（A/B/C = 17/16/39），GMV 合计 R$ 13,330,627.12。")


# ==============================================================================
# 模块 10：fig20 GMV 预测带区间
# ==============================================================================

def fig20_forecast_interval() -> None:
    df = load_table("forecast.csv")
    df["month"] = df["month"].astype(str)
    hist = df[~df["is_forecast"]].copy()
    fut = df[df["is_forecast"]].copy()

    fig, ax = plt.subplots(figsize=(12.2, 6.2))
    x = np.arange(len(df))
    xh = np.arange(len(hist))
    xf = np.arange(len(hist) - 1, len(df))   # 从最后一个历史点接上，保证连续

    ax.plot(xh, hist["actual"], color=C_DARK, linewidth=2.2, marker="o", markersize=4,
            label="实际 GMV")
    ax.plot(xh, hist["forecast"], color=C_MID, linewidth=1.8, linestyle="--",
            label="模型拟合值")

    # 未来段：把最后一个历史点接到预测起点，视觉上连续
    ax.plot(xf, np.r_[hist["actual"].iloc[-1], fut["forecast"].values],
            color=C_ORANGE, linewidth=2.4, marker="o", markersize=6, label="预测 GMV")
    ax.fill_between(xf,
                    np.r_[hist["actual"].iloc[-1], fut["lower95"].values],
                    np.r_[hist["actual"].iloc[-1], fut["upper95"].values],
                    color=C_ORANGE, alpha=0.3, label="95% 置信区间")

    ax.axvline(len(hist) - 1, color="#999999", linestyle=":", linewidth=1.2)
    ax.text(len(hist) - 1.1, ax.get_ylim()[1] * 0.99, "预测起点", fontsize=8.5,
            color="#666666", rotation=90, va="top", ha="right")

    # 三个预测值单独列框（逐点标注会互相压字）
    lines = [f"{m}   R$ {v / 1e6:.2f}M" for m, v in zip(fut["month"], fut["forecast"])]
    ax.text(0.025, 0.70, "3 个月预测\n" + "\n".join(lines), transform=ax.transAxes,
            fontsize=9, color=C_ORANGE, va="top", ha="left", linespacing=1.5,
            bbox=dict(boxstyle="round,pad=0.45", fc="white", ec=C_ORANGE, alpha=0.92))

    step = 2
    ax.set_xticks(x[::step])
    ax.set_xticklabels(df["month"][::step], rotation=45, ha="right", fontsize=8.5)
    ax.set_ylabel("月度 GMV（R$）")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, p: f"{v / 1e6:.1f}M"))
    ax.set_title("月度 GMV：Holt 阻尼趋势预测未来 3 个月", loc="left")
    ax.text(0.0, 1.005,
            "MAPE 28.79% / RMSE R$ 296,677（3 个月回测）；区间为残差近似法，sigma = R$ 145,083",
            transform=ax.transAxes, fontsize=9, color="#666666")
    finish(ax)
    ax.legend(loc="upper left")

    save(fig, "fig20_forecast_interval.png",
         "数据源：forecast.csv；实际/拟合为 2017-01~2018-08，预测为 2018-09~11；"
         "GMV 含运费（payment_total），与品类图的 price 口径不同。")


# ==============================================================================
# 模块 11：主流程
# ==============================================================================

TASKS = {
    "01": ("fig12_rfm_bubble.png", fig12_rfm_bubble),
    "02": ("fig13_rfm_gmv_bar.png", fig13_rfm_gmv_bar),
    "03": ("fig14_cohort_heatmap.png", fig14_cohort_heatmap),
    "04": ("fig15_cohort_line.png", fig15_cohort_line),
    "05": ("fig16_boston_bubble.png", fig16_boston_bubble),
    "06": ("fig17_boston_bar.png", fig17_boston_bar),
    "07": ("fig18_pareto_line.png", fig18_pareto_line),
    "08": ("fig19_abc_stacked.png", fig19_abc_stacked),
    "09": ("fig20_forecast_interval.png", fig20_forecast_interval),
}


def main() -> int:
    parser = argparse.ArgumentParser(description="生成 fig12–fig20 业务模型图")
    parser.add_argument("--only", nargs="*", default=None,
                        help="只生成指定编号，如 --only 01 05；缺省生成全部")
    args = parser.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"visuals_{datetime.now():%Y%m%d_%H%M%S}.log"
    FIG_DIR.mkdir(parents=True, exist_ok=True)

    setup_style()
    keys = [k for k in TASKS if (args.only is None or k in args.only)]
    if not keys:
        raise SystemExit(f"未匹配任何图号：{args.only}，可选 {list(TASKS)}")

    lines = [
        "=" * 78,
        f"07_visuals.py 运行时间：{datetime.now():%Y-%m-%d %H:%M:%S}",
        f"工作目录：{Path.cwd()}",
        f"输出目录：{FIG_DIR}　DPI：{DPI}",
        f"计划生成：{len(keys)} 张（{', '.join(keys)}）",
        "=" * 78,
    ]
    print("\n".join(lines))

    for k in keys:
        filename, func = TASKS[k]
        print(f"\n[fig{k}] {filename}")
        func()

    print("\n" + "=" * 78)
    print(f"完成：{len(FIGURES)} 张")
    for name, size in FIGURES:
        print(f"  {name:<34}{size / 1024:8.1f} KB")
    print("=" * 78)

    with open(log_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n\n")
        for name, size in FIGURES:
            f.write(f"{name}\t{size / 1024:.1f} KB\n")
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
