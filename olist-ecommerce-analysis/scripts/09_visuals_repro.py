# -*- coding: utf-8 -*-
"""
09_visuals_repro.py —— 用 Olist 真实数据复现《Excel 数据可视化——从图表到数据大屏》
中的 11 种图表模板（原书模板编号 01/02/05/11/13/14/17/23/26/29/30）。

===============================================================================
输入（全部取自真实清洗结果，脚本内不生成、不补造任何数据）
-------------------------------------------------------------------------------
data/clean/orders_clean.csv    订单主表（主分析集 97,308 单，2017-01 ~ 2018-08）
outputs/tables/abc.csv         品类 ABC 分级结果（含 gmv / share）
outputs/tables/rfm.csv         客户级 RFM 明细（用于计算复购率）

输出
-------------------------------------------------------------------------------
outputs/figures/fig01_*.png ~ fig11_*.png   共 11 张，150 dpi（图号与论文一致）
logs/repro_YYYYmmdd_HHMMSS.log       运行日志

依赖
-------------------------------------------------------------------------------
pandas  numpy  matplotlib  seaborn  scipy

运行
-------------------------------------------------------------------------------
cd <仓库根目录>
python scripts/09_visuals_repro.py
python scripts/09_visuals_repro.py --only 05 17    # 只重画指定模板

口径约定（与 03~07 保持一致，务必看清）
-------------------------------------------------------------------------------
1. 图 01/05/13/23/26/30 的金额用 orders_clean.payment_total（支付金额，含运费）；
   图 02/17 的品类金额用 abc.csv 的 gmv（商品金额 price，不含运费）。
   两套口径不可互相加减，各自在图注中标注。
2. 图 05 的支付方式取 orders_clean.payment_type_main（每单唯一的主支付方式），
   因此不存在一单多笔支付被重复计入的问题。
3. 图 11/23 的「12 个月」统一取最近 12 个完整月 2017-09 ~ 2018-08。
4. 图 13/30 的两期对比统一取 1-8 月等长窗口，规避 2018 年数据截断造成的低估。
===============================================================================
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")          # 无 GUI 后端，服务器/终端均可运行
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib.colors import LinearSegmentedColormap
from scipy.interpolate import make_interp_spline, PchipInterpolator

# 双 R$ 的字符串（如「R$ 1.2M／合计 R$ 13M」）会触发 mathtext 的探测式排版，
# 在 stderr 刷一串「Font 'rm' does not have a glyph」告警。实际渲染走普通文本
# 通道、结果正确，这里只把噪声降级，不影响任何出图内容。
logging.getLogger("matplotlib.mathtext").setLevel(logging.ERROR)

# =============================================================================
# 模块 0：路径与全局样式
# =============================================================================

# 约定：在仓库根目录执行（与 01~08 号脚本一致，全部相对路径）。
# 同时兼容从 scripts/ 目录直接运行的情形，避免找不到 data/。
ROOT = Path.cwd()
if not (ROOT / "data" / "clean").exists():
    _alt = Path(__file__).resolve().parent.parent
    if (_alt / "data" / "clean").exists():
        ROOT = _alt

DATA_DIR = ROOT / "data" / "clean"
TABLE_DIR = ROOT / "outputs" / "tables"
FIG_DIR = ROOT / "outputs" / "figures"
LOG_DIR = ROOT / "logs"
for d in (FIG_DIR, LOG_DIR):
    d.mkdir(parents=True, exist_ok=True)

CSV_ENCODING = "utf-8-sig"     # 清洗表带 BOM，读写都必须用它，否则首列名带 \ufeff

# 与 07_visuals.py 同一套色板，保证整本论文的视觉一致
C_DARK = "#1F3864"      # 深蓝
C_BLUE = "#2E75B6"      # 主蓝
C_MID = "#5B9BD5"       # 中蓝
C_LIGHT = "#BDD7EE"     # 浅蓝
C_ORANGE = "#ED7D31"    # 强调橙
C_GRAY = "#A6A6A6"
C_TRACK = "#EDEDED"
GRID = "#D9D9D9"
TXT = "#333333"

# 最近 12 个完整月
R12_START, R12_END = "2017-09", "2018-08"

_LOG_LINES: list[str] = []


def log(msg: str = "") -> None:
    """同时打印并留档，便于回填论文与排错。"""
    print(msg)
    _LOG_LINES.append(msg)


def _pick_font() -> str:
    """挑一个本机可用的中文字体，避免出现方块字。"""
    installed = {f.name for f in fm.fontManager.ttflist}
    for name in ("Microsoft YaHei", "微软雅黑", "SimHei", "Noto Sans CJK SC", "PingFang SC"):
        if name in installed:
            return name
    return "DejaVu Sans"      # 兜底：英文正常，中文会告警


def setup_style() -> None:
    """全局样式：微软雅黑、白底无填充、仅横向网格 #D9D9D9 0.5pt。"""
    font = _pick_font()
    plt.rcParams.update({
        "font.family": font,
        "font.size": 10,
        "axes.unicode_minus": False,
        # 关闭 $...$ 数学解析：图注里出现两个 R$ 时，matplotlib 会把中间内容
        # 当公式渲染成斜体乱码（07_visuals.py 已踩过这个坑）。
        "text.parse_math": False,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": "#BFBFBF",
        "axes.linewidth": 0.8,
        "axes.grid": True,
        "axes.grid.axis": "y",
        "grid.color": GRID,
        "grid.linewidth": 0.5,
        "grid.alpha": 1.0,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.color": "#595959",
        "ytick.color": "#595959",
        "legend.frameon": False,
        "figure.dpi": 110,
        "savefig.dpi": 150,
    })
    log(f"[样式] 中文字体 = {font}；网格 #D9D9D9 / 0.5pt；图表区白色无填充")


# =============================================================================
# 模块 1：通用工具
# =============================================================================

def money(v: float, force_unit: str | None = None) -> str:
    """把金额压成 R$ 1.23M / R$ 45K / R$ 678 三种写法，避免长数字压轴。"""
    if force_unit == "M" or (force_unit is None and abs(v) >= 1e6):
        return f"R$ {v / 1e6:.2f}M"
    if force_unit == "K" or (force_unit is None and abs(v) >= 1e3):
        return f"R$ {v / 1e3:.0f}K"
    return f"R$ {v:,.0f}"


def frame(fig, ax, title: str = "", sub: str = "", note: str = "", *,
          top: float = 0.85, bottom: float = 0.14, left: float = 0.08,
          right: float = 0.98, pad: int = 30) -> None:
    """
    统一版式：标题（带 pad）+ 副标题（贴轴顶）+ 图注（贴画布底）。
    标题与副标题若都用固定 figure 坐标，字号一变就会互相压字；改成
    「标题走 pad、副标题走轴坐标」的配合，二者在任意尺寸下都不会撞。
    """
    fig.subplots_adjust(top=top, bottom=bottom, left=left, right=right)
    if title:
        ax.set_title(title, loc="left", fontsize=15, weight="bold",
                     color=C_DARK, pad=pad)
    if sub:
        ax.text(0.0, 1.010, sub, transform=ax.transAxes, ha="left", va="bottom",
                fontsize=9, color="#666666")
    if note:
        fig.text(0.006, 0.008, note, fontsize=7.2, color="#7F7F7F",
                 ha="left", va="bottom")


def frame_pie(fig, title: str, sub: str = "", note: str = "") -> None:
    """饼图/环形图的版式：饼图 axes 是正方形且居中，set_title 会缩到中间，
    所以标题改用画布坐标，才能与其余 9 张左对齐。"""
    fig.subplots_adjust(top=0.82, bottom=0.10)
    fig.text(0.02, 0.965, title, fontsize=15, weight="bold", color=C_DARK,
             ha="left", va="top")
    if sub:
        fig.text(0.02, 0.905, sub, fontsize=9, color="#666666", ha="left", va="top")
    if note:
        fig.text(0.006, 0.008, note, fontsize=7.2, color="#7F7F7F",
                 ha="left", va="bottom")


def save(fig, name: str) -> None:
    out = FIG_DIR / name
    fig.savefig(out, dpi=150, bbox_inches="tight", pad_inches=0.22, facecolor="white")
    plt.close(fig)
    log(f"    → {out.name}")


def gradient_bars(ax, xs, hs, width: float = 0.62) -> None:
    """
    渐变柱：matplotlib 没有原生柱状渐变，用 imshow 铺一张竖向渐变图，
    extent 恰好等于柱体包围盒，等效于给每根柱子填了线性渐变。
    """
    cmap = LinearSegmentedColormap.from_list("bar_grad", [C_LIGHT, C_BLUE])
    grad = np.linspace(0.0, 1.0, 256).reshape(-1, 1)
    for x, h in zip(xs, hs):
        ax.imshow(grad, extent=(x - width / 2, x + width / 2, 0, h),
                  origin="lower", aspect="auto", cmap=cmap, alpha=0.92,
                  interpolation="bilinear", zorder=3)


def fmt_k(v, _=None) -> str:
    """千位缩放，并把 -0 归零（柱状图基线偶尔会落在 -1e-12）。"""
    if abs(v) < 1:
        return "0"
    return f"{v / 1e3:.0f}K"


# =============================================================================
# 模块 2：读取真实数据
# =============================================================================

def load_orders() -> pd.DataFrame:
    usecols = ["order_id", "customer_state", "payment_total", "payment_type_main",
               "review_score", "purchase_ym"]
    df = pd.read_csv(DATA_DIR / "orders_clean.csv", encoding=CSV_ENCODING, usecols=usecols)
    df["purchase_ym"] = df["purchase_ym"].astype(str)
    log(f"[读取] orders_clean.csv  {len(df):,} 行 / {df['purchase_ym'].nunique()} 个月 "
        f"/ {df['customer_state'].nunique()} 个州（{df['purchase_ym'].min()} ~ {df['purchase_ym'].max()}）")
    return df


def load_abc() -> pd.DataFrame:
    abc = pd.read_csv(TABLE_DIR / "abc.csv", encoding=CSV_ENCODING)
    log(f"[读取] abc.csv  {len(abc)} 个品类，GMV 合计 {money(abc['gmv'].sum())}")
    return abc


def load_rfm() -> pd.DataFrame:
    rfm = pd.read_csv(TABLE_DIR / "rfm.csv", encoding=CSV_ENCODING,
                      usecols=["customer_unique_id", "F"])
    log(f"[读取] rfm.csv  {len(rfm):,} 位客户")
    return rfm


def monthly(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    """按月聚合：GMV（支付口径）、订单数、客单价。"""
    sub = df[(df["purchase_ym"] >= start) & (df["purchase_ym"] <= end)]
    g = (sub.groupby("purchase_ym")
            .agg(gmv=("payment_total", "sum"), orders=("order_id", "nunique"))
            .reset_index()
            .sort_values("purchase_ym"))
    g["aov"] = g["gmv"] / g["orders"]
    return g


# =============================================================================
# 模块 3：11 个模板复现函数
# =============================================================================

def fig_01_gradient_bar(o: pd.DataFrame) -> None:
    """模板 01｜渐变柱形图：12 个月 GMV，柱顶直标数值，隐藏 Y 轴。"""
    d = monthly(o, R12_START, R12_END)
    x = np.arange(len(d))

    fig, ax = plt.subplots(figsize=(12.4, 5.0))
    gradient_bars(ax, x, d["gmv"].values)

    for xi, v in zip(x, d["gmv"].values):
        ax.text(xi, v * 1.015, f"{v / 1e6:.2f}M", ha="center", va="bottom",
                fontsize=9, color=C_DARK, weight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(d["purchase_ym"], fontsize=9)
    ax.set_ylim(0, d["gmv"].max() * 1.18)
    ax.set_xlim(-0.7, len(d) - 0.3)
    ax.yaxis.set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.grid(False)

    frame(fig, ax,
          "GMV 三个月完成爬坡，此后 8 个月在高位窄幅震荡",
          f"最近 12 个完整月（{R12_START} ~ {R12_END}）　单位：百万雷亚尔（R$ M）",
          "模板 01｜渐变柱形图　数据源：orders_clean.csv　口径：payment_total（含运费）　"
          "柱体由 #BDD7EE 自下而上渐变至 #2E75B6",
          top=0.82, bottom=0.10, left=0.03, right=0.99)
    save(fig, "fig01_gradient_bar.png")


def fig_02_avg_line_bar(abc: pd.DataFrame) -> None:
    """模板 02｜带平均线柱形图：Top 8 品类 GMV + 橙色虚线平均值。"""
    d = abc.nlargest(8, "gmv").reset_index(drop=True)
    avg = float(d["gmv"].mean())
    n_above = int((d["gmv"] > avg).sum())
    x = np.arange(len(d))

    fig, ax = plt.subplots(figsize=(12.4, 5.6))
    bars = ax.bar(x, d["gmv"], width=0.6, color=C_BLUE, zorder=3)
    bars[0].set_color(C_DARK)          # 第一名加深，强化视觉层级

    for xi, v in zip(x, d["gmv"]):
        ax.text(xi, v * 1.01, f"{v / 1e6:.2f}M", ha="center", va="bottom",
                fontsize=9, color=TXT)

    ax.axhline(avg, color=C_ORANGE, linestyle="--", linewidth=1.4, zorder=4)
    ax.text(len(d) - 0.45, avg * 1.03, f"平均 {money(avg)}  ", color=C_ORANGE,
            fontsize=10, weight="bold", ha="right", va="bottom")

    ax.set_xticks(x)
    ax.set_xticklabels([c if len(c) <= 15 else c[:14] + "…" for c in d["category"]],
                       rotation=24, ha="right", fontsize=9)
    ax.set_ylim(0, d["gmv"].max() * 1.16)
    ax.set_ylabel("GMV（R$）", fontsize=10, color=TXT)
    ax.grid(True, axis="y", color=GRID, linewidth=0.5)
    ax.set_axisbelow(True)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v / 1e6:.1f}M")

    frame(fig, ax,
          f"头部 8 个品类里，只有 {n_above} 个站上均值线",
          f"平均线 = 这 8 个品类商品金额的算术均值（{money(avg)}），不是全品类均值",
          "模板 02｜带平均线柱形图　数据源：outputs/tables/abc.csv　口径：price（商品金额，不含运费）",
          top=0.84, bottom=0.26, left=0.08)
    save(fig, "fig02_avg_line_bar.png")


def fig_05_stacked_bar(o: pd.DataFrame) -> None:
    """模板 05｜层叠柱形图：Top 4 州 × 3 种支付方式。"""
    segs = ["credit_card", "boleto", "voucher"]
    sub = o[o["payment_type_main"].isin(segs)]
    piv = (sub.pivot_table(index="customer_state", columns="payment_type_main",
                           values="payment_total", aggfunc="sum")
              .fillna(0.0))
    piv["_total"] = piv[segs].sum(axis=1)
    top4 = piv.nlargest(4, "_total").sort_values("_total", ascending=False)
    excluded = int((~o["payment_type_main"].isin(segs)).sum())

    colors = {"credit_card": C_DARK, "boleto": C_MID, "voucher": C_LIGHT}
    names = {"credit_card": "信用卡", "boleto": "票据（boleto）", "voucher": "代金券"}

    fig, ax = plt.subplots(figsize=(10.8, 5.8))
    bottom = np.zeros(len(top4))
    for s in segs:
        vals = top4[s].values
        ax.bar(top4.index, vals, bottom=bottom, width=0.56,
               color=colors[s], label=names[s], zorder=3,
               edgecolor="white", linewidth=0.8)
        bottom += vals

    for i, t in enumerate(top4["_total"].values):
        ax.text(i, t * 1.012, money(t), ha="center", va="bottom",
                fontsize=9.5, color=C_DARK, weight="bold")

    ax.set_ylim(0, top4["_total"].max() * 1.16)
    ax.set_ylabel("GMV（R$）", fontsize=10, color=TXT)
    ax.grid(True, axis="y", color=GRID, linewidth=0.5)
    ax.set_axisbelow(True)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v / 1e6:.0f}M" if abs(v) >= 1 else "0")
    ax.legend(loc="upper right", fontsize=9.5, labelspacing=0.6)

    credit = top4["credit_card"].sum() / top4["_total"].sum() * 100
    frame(fig, ax,
          "圣保罗一州独大，四州均以信用卡为绝对主力",
          f"Top4 州的信用卡占比 {credit:.1f}%；debit_card {excluded:,} 单（{excluded / len(o) * 100:.1f}%）未计入",
          "模板 05｜层叠柱形图　数据源：orders_clean.csv(payment_type_main)　口径：payment_total　"
          "按订单主支付方式拆分，一单只归一类，不存在重复计入",
          top=0.84, bottom=0.11, left=0.09)
    save(fig, "fig03_stacked_bar.png")


def fig_11_smooth_line(o: pd.DataFrame) -> None:
    """模板 11｜平滑折线图：12 个月订单量，三次样条 + 底部渐隐，只标峰谷。"""
    d = monthly(o, R12_START, R12_END)
    x = np.arange(len(d), dtype=float)
    y = d["orders"].values.astype(float)

    xs = np.linspace(x.min(), x.max(), 320)
    ys = make_interp_spline(x, y, k=3)(xs)
    span = y.max() - y.min()
    if ys.min() < y.min() - 0.02 * span or ys.max() > y.max() + 0.02 * span:
        # 三次样条在陡升／陡降段会过冲，凭空造出数据里不存在的峰谷（本数据
        # 2017-09→10 就被压到低于实际最小值）。改用 PCHIP 保形插值：同样平滑，
        # 但绝不越过实测极值，避免图面误导。
        ys = PchipInterpolator(x, y)(xs)
        log("      [提示] 三次样条过冲，已自动切换为 PCHIP 保形插值")

    fig, ax = plt.subplots(figsize=(12.4, 5.2))
    ax.fill_between(xs, ys, color=C_BLUE, alpha=0.10, zorder=2)
    ax.plot(xs, ys, color=C_BLUE, linewidth=2.4, zorder=4)
    ax.plot(x, y, "o", color="white", markeredgecolor=C_BLUE,
            markeredgewidth=1.6, markersize=6, zorder=5)

    i_max, i_min = int(np.argmax(y)), int(np.argmin(y))
    ax.annotate(f"{d['purchase_ym'].iloc[i_max]}　{int(y[i_max]):,} 单",
                xy=(x[i_max], y[i_max]), xytext=(0, 16), textcoords="offset points",
                ha="center", va="bottom", fontsize=9.5, color=C_DARK, weight="bold")
    ax.annotate(f"{d['purchase_ym'].iloc[i_min]}　{int(y[i_min]):,} 单",
                xy=(x[i_min], y[i_min]), xytext=(14, -4), textcoords="offset points",
                ha="left", va="center", fontsize=9.5, color=C_DARK, weight="bold")

    ax.set_xticks(x)
    ax.set_xticklabels(d["purchase_ym"], fontsize=9)
    ax.set_ylim(y.min() * 0.90, y.max() * 1.16)
    ax.set_xlim(-0.5, len(d) - 0.5)
    ax.set_ylabel("订单数（单）", fontsize=10, color=TXT)
    ax.grid(True, axis="y", color=GRID, linewidth=0.5)
    ax.set_axisbelow(True)
    ax.yaxis.set_major_formatter(fmt_k)

    frame(fig, ax,
          f"{d['purchase_ym'].iloc[i_max]} 冲上 {int(y[i_max]):,} 单，此后在 6-7 千单区间震荡",
          "曲线为插值平滑（仅视觉，不参与任何计算）；圆点为月度实际值",
          "模板 11｜平滑折线图　数据源：orders_clean.csv　"
          f"峰 {int(y[i_max]):,} 单（{d['purchase_ym'].iloc[i_max]}）／谷 {int(y[i_min]):,} 单（{d['purchase_ym'].iloc[i_min]}）",
          top=0.83, bottom=0.13, left=0.08)
    save(fig, "fig04_smooth_line.png")


def fig_13_compare_line(o: pd.DataFrame) -> None:
    """模板 13｜对比折线图：2018 与 2017 年 1-8 月 GMV（等长窗口）。"""
    cur = monthly(o, "2018-01", "2018-08")
    base = monthly(o, "2017-01", "2017-08")
    months = np.arange(1, 9)

    fig, ax = plt.subplots(figsize=(11.0, 5.6))
    ax.fill_between(months, base["gmv"].values, cur["gmv"].values,
                    color=C_BLUE, alpha=0.07, zorder=2)
    ax.plot(months, base["gmv"].values, color=C_GRAY, linestyle="--",
            linewidth=1.8, marker="o", markersize=4.5, label="2017 年 1-8 月", zorder=3)
    ax.plot(months, cur["gmv"].values, color=C_BLUE, linestyle="-",
            linewidth=2.6, marker="o", markersize=6.5, label="2018 年 1-8 月", zorder=4)

    g = cur["gmv"].sum() / base["gmv"].sum() - 1
    ax.annotate(f"8 个月合计同比 {g * 100:+.1f}%",
                xy=(8, cur["gmv"].iloc[-1]), xytext=(-6, 38), textcoords="offset points",
                ha="right", fontsize=10.5, color=C_ORANGE, weight="bold",
                bbox=dict(boxstyle="round,pad=0.35", fc="white", ec=C_ORANGE, alpha=0.92))

    ax.set_xticks(months)
    ax.set_xticklabels([f"{m} 月" for m in months], fontsize=9.5)
    ax.set_ylim(0, cur["gmv"].max() * 1.24)
    ax.set_ylabel("月度 GMV（R$）", fontsize=10, color=TXT)
    ax.grid(True, axis="y", color=GRID, linewidth=0.5)
    ax.set_axisbelow(True)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v / 1e6:.1f}M")
    ax.legend(loc="upper left", fontsize=9.5)

    frame(fig, ax,
          "2018 年前 8 个月月月高过年内同期，6 月起回落至百万雷亚尔附近",
          "两期均取 1-8 月等长窗口，规避 2018 年 9 月后数据截断造成的低估",
          f"模板 13｜对比折线图　数据源：orders_clean.csv　口径：payment_total（含运费）　"
          f"8 个月合计 {money(cur['gmv'].sum())} vs {money(base['gmv'].sum())}；"
          f"与 §3.3 波士顿矩阵的商品金额口径（+140.6%）不同源，不可互校",
          top=0.84, bottom=0.11, left=0.09)
    save(fig, "fig05_compare_line.png")


def fig_14_donut(rfm: pd.DataFrame) -> None:
    """模板 14｜单值圆环图：整体复购率（F≥2），中心大字百分比。"""
    rate = float((rfm["F"] >= 2).mean() * 100)
    n_rep = int((rfm["F"] >= 2).sum())

    fig, ax = plt.subplots(figsize=(5.8, 5.8))
    ax.pie([rate, 100 - rate], colors=[C_BLUE, "#E7E6E6"], startangle=90,
           counterclock=False,
           wedgeprops=dict(width=0.30, edgecolor="white", linewidth=1.6))
    ax.text(0, 0.10, f"{rate:.2f}%", ha="center", va="center",
            fontsize=34, weight="bold", color=C_DARK)
    ax.text(0, -0.24, "客户复购率", ha="center", va="center", fontsize=11, color="#666666")
    ax.text(0, -0.44, f"{n_rep:,} 户 / {len(rfm):,} 户", ha="center", va="center",
            fontsize=9, color=C_GRAY)
    ax.set_aspect("equal")

    frame_pie(fig, "每 100 位客户里，只有 3 位回头",
              "圆环代表 100% 客户，深蓝扇区为窗口内买过 2 单及以上的客户",
              "模板 14｜单值圆环图　数据源：outputs/tables/rfm.csv　口径：F≥2 记为复购，"
              "分母为窗口内 94,136 位有交易客户")
    save(fig, "fig06_donut.png")


def fig_17_jade_ring(abc: pd.DataFrame) -> None:
    """模板 17｜玉玦图：Top1 品类 GMV 占比，三扇形（值 / 缺口 / 余量）。"""
    d = abc.nlargest(1, "gmv").iloc[0]
    share = float(d["share"] * 100)
    gap = 2.0                       # 玉玦缺口，纯装饰
    rest = 100 - share - gap

    fig, ax = plt.subplots(figsize=(5.8, 5.8))
    ax.pie([share, gap, rest], colors=[C_BLUE, "white", "#E7E6E6"],
           startangle=90, counterclock=False,
           wedgeprops=dict(width=0.20, edgecolor="white", linewidth=1.5))
    ax.text(0, 0.10, f"{share:.2f}%", ha="center", va="center",
            fontsize=30, weight="bold", color=C_DARK)
    ax.text(0, -0.18, "占全部品类 GMV", ha="center", va="center", fontsize=10, color="#666666")
    ax.text(0, -0.36, str(d["category"]), ha="center", va="center", fontsize=9, color=C_BLUE)
    ax.set_aspect("equal")

    frame_pie(fig, f"第一大品类 {d['category']} 也只占 {share:.1f}%",
              "72 个品类中没有绝对主角，结构分散是这份数据的底色",
              f"模板 17｜玉玦图　数据源：outputs/tables/abc.csv　口径：price（不含运费）　"
              f"该品类 GMV {money(d['gmv'])}；白色缺口为装饰，非数据")
    save(fig, "fig07_jade_ring.png")


def fig_23_bar_line(o: pd.DataFrame) -> None:
    """模板 23｜柱形折线图：12 个月订单量（柱）+ 客单价（线），双 Y 轴。"""
    d = monthly(o, R12_START, R12_END)
    x = np.arange(len(d))
    i_pk = int(np.argmax(d["orders"].values))
    drop = d["aov"].iloc[i_pk - 1] - d["aov"].iloc[i_pk] if i_pk > 0 else 0.0

    fig, ax1 = plt.subplots(figsize=(12.4, 5.6))
    ax1.bar(x, d["orders"], width=0.58, color=C_BLUE, zorder=3, label="订单数（左轴）")
    ax1.set_ylim(0, d["orders"].max() * 1.22)
    ax1.set_xticks(x)
    ax1.set_xticklabels(d["purchase_ym"], fontsize=9)
    ax1.set_ylabel("订单数（单）", fontsize=10, color=TXT)
    ax1.grid(True, axis="y", color=GRID, linewidth=0.5)
    ax1.set_axisbelow(True)
    ax1.yaxis.set_major_formatter(fmt_k)

    ax2 = ax1.twinx()
    ax2.plot(x, d["aov"], color=C_ORANGE, linewidth=2.2, marker="o",
             markersize=6.5, markerfacecolor="white", markeredgewidth=2,
             markeredgecolor=C_ORANGE, zorder=5, label="客单价（右轴）")
    for xi, v in zip(x, d["aov"]):
        # 折线压在深蓝柱上，橙字直接写会糊；加半透明白底保证可读
        ax2.annotate(f"{v:.0f}", (xi, v), xytext=(0, 11), textcoords="offset points",
                     ha="center", fontsize=8, color=C_ORANGE,
                     bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="none", alpha=0.80))
    lo, hi = d["aov"].min(), d["aov"].max()
    pad_ = (hi - lo) * 0.55 if hi > lo else 10
    ax2.set_ylim(lo - pad_, hi + pad_)
    ax2.set_ylabel("客单价（R$）", fontsize=10, color=C_ORANGE)
    ax2.tick_params(axis="y", colors=C_ORANGE, labelsize=9)
    ax2.spines["right"].set_visible(True)
    ax2.spines["right"].set_color("#E0E0E0")
    ax2.grid(False)

    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, loc="upper left", fontsize=9.5, ncol=2)

    frame(fig, ax1,
          f"{d['purchase_ym'].iloc[i_pk]} 订单冲到 {int(d['orders'].iloc[i_pk]):,} 单，客单价反降 R$ {drop:.0f}",
          "左右轴量纲不同，仅用于观察同向或反向关系，不可直接比较刻度",
          f"模板 23｜柱形折线图　数据源：orders_clean.csv　客单价 = payment_total ÷ 订单数（含运费）　"
          f"12 个月均值 R$ {d['aov'].mean():.2f}",
          top=0.83, bottom=0.12, left=0.08, right=0.93)
    save(fig, "fig08_bar_line.png")


def fig_26_bar_dot(o: pd.DataFrame) -> None:
    """模板 26｜柱形圆图：Top 5 州 GMV，柱顶叠加深蓝圆点（白描边）。"""
    s = o.groupby("customer_state")["payment_total"].sum().nlargest(5)
    x = np.arange(len(s))
    top5 = s.sum() / o["payment_total"].sum() * 100

    fig, ax = plt.subplots(figsize=(10.6, 5.8))
    ax.bar(x, s.values, width=0.54, color=C_LIGHT, zorder=3,
           edgecolor=C_MID, linewidth=1.0)
    ax.scatter(x, s.values, s=210, color=C_DARK, edgecolor="white",
               linewidth=2.2, zorder=6)

    for xi, v in zip(x, s.values):
        ax.text(xi, v * 0.87, money(v), ha="center", va="top",
                fontsize=10, color=C_DARK, weight="bold", zorder=7)

    ax.set_xticks(x)
    ax.set_xticklabels(s.index, fontsize=12, color=C_DARK, weight="bold")
    ax.set_ylim(0, s.max() * 1.14)
    ax.set_xlim(-0.6, len(s) - 0.4)
    ax.set_ylabel("GMV（R$）", fontsize=10, color=TXT)
    ax.grid(True, axis="y", color=GRID, linewidth=0.5)
    ax.set_axisbelow(True)
    ax.yaxis.set_major_formatter(lambda v, _: f"{v / 1e6:.0f}M" if abs(v) >= 1 else "0")

    cond = "超过" if s.iloc[0] > s.iloc[1:].sum() else "接近"
    frame(fig, ax,
          f"前 5 个州拿走 {top5:.0f}% 的 GMV，圣保罗一州{cond}后四名之和",
          f"共 27 个州；SP 单州 {money(s.iloc[0])}，后四名合计 {money(s.iloc[1:].sum())}",
          "模板 26｜柱形圆图　数据源：orders_clean.csv　口径：payment_total（含运费）　"
          "柱顶圆点为装饰元素，不代表额外数据",
          top=0.84, bottom=0.11, left=0.09)
    save(fig, "fig09_bar_dot.png")


def fig_29_slider_dot(o: pd.DataFrame) -> None:
    """模板 29｜滑珠图：4 个州的平均评价分（1-5 分 ×20 = 百分制）。"""
    g = (o.dropna(subset=["review_score"])
           .groupby("customer_state")["review_score"].agg(["mean", "count"]))
    top4 = g.nlargest(4, "count").sort_values("mean")
    vals = (top4["mean"] * 20).values
    y = np.arange(len(top4))

    fig, ax = plt.subplots(figsize=(10.8, 4.8))
    ax.barh(y, [100] * len(y), height=0.40, color=C_TRACK, zorder=2)
    ax.scatter(vals, y, s=320, color=C_DARK, edgecolor="white", linewidth=2.4, zorder=5)

    for yi, v, m in zip(y, vals, top4["mean"].values):
        ax.text(v + 2.4, yi, f"{m:.2f} 分", va="center", ha="left",
                fontsize=10, color=C_DARK, weight="bold")

    ax.set_yticks(y)
    ax.set_yticklabels(top4.index, fontsize=12, color=C_DARK, weight="bold")
    ax.set_xlim(0, 108)
    ax.set_xticks([0, 20, 40, 60, 80, 100])
    ax.set_xticklabels(["0", "20", "40", "60", "80", "100"], fontsize=9)
    ax.grid(True, axis="x", color=GRID, linewidth=0.5)
    ax.grid(False, axis="y")
    ax.set_axisbelow(True)
    ax.set_xlabel("满意度得分（5 分制 ×20 换算为百分制）", fontsize=10, color=TXT)

    miss = float(o["review_score"].isna().mean() * 100)
    frame(fig, ax,
          f"四个最大州的满意度集中在 {vals.min():.1f}–{vals.max():.1f} 分，极差仅 {vals.max() - vals.min():.1f} 分",
          "灰轨固定为 100 分满格，用于横向比较",
          f"模板 29｜滑珠图　数据源：orders_clean.csv(review_score)　"
          f"四州有效评价 {int(top4['count'].sum()):,} 单；全量缺失评价 {int(o['review_score'].isna().sum()):,} 单（{miss:.1f}%）",
          top=0.82, bottom=0.22, left=0.09, right=0.97)
    save(fig, "fig10_slider_dot.png")


def fig_30_dumbbell(o: pd.DataFrame) -> None:
    """模板 30｜对比滑珠图：4 个州 2018 vs 2017 年平均客单价（哑铃状）。"""
    states = o.groupby("customer_state")["payment_total"].sum().nlargest(4).index.tolist()
    base = o[(o["purchase_ym"] >= "2017-01") & (o["purchase_ym"] <= "2017-08")]
    cur = o[(o["purchase_ym"] >= "2018-01") & (o["purchase_ym"] <= "2018-08")]

    def aov(df):
        g = df[df["customer_state"].isin(states)].groupby("customer_state")["payment_total"]
        return (g.sum() / g.count()).reindex(states)

    a17, a18 = aov(base), aov(cur)
    order = a18.sort_values().index.tolist()
    a17, a18 = a17.reindex(order), a18.reindex(order)
    dlt = a18 / a17 - 1
    y = np.arange(len(order))

    fig, ax = plt.subplots(figsize=(10.8, 5.0))
    for yi, v17, v18 in zip(y, a17.values, a18.values):
        ax.plot([v17, v18], [yi, yi], color="#D0D0D0", linewidth=3.2,
                solid_capstyle="round", zorder=2)
    ax.scatter(a17.values, y, s=190, color=C_GRAY, edgecolor="white",
               linewidth=2, zorder=4, label="2017 年 1-8 月")
    ax.scatter(a18.values, y, s=190, color=C_BLUE, edgecolor="white",
               linewidth=2, zorder=5, label="2018 年 1-8 月")

    for yi, v17, v18 in zip(y, a17.values, a18.values):
        d = v18 / v17 - 1
        # 变动极小时保留两位小数：SP 两期几乎重合，写成 +0.0% 会被误读成"没算"
        lab = f"{d * 100:+.2f}%" if abs(d) < 0.001 else f"{d * 100:+.1f}%"
        ax.text(max(v17, v18) + 1.8, yi, lab, va="center", ha="left",
                fontsize=9.5, color=C_ORANGE if d >= 0.001 else "#7F7F7F", weight="bold")

    ax.set_yticks(y)
    ax.set_yticklabels(order, fontsize=12, color=C_DARK, weight="bold")
    lo = min(a17.min(), a18.min())
    hi = max(a17.max(), a18.max())
    span = hi - lo
    ax.set_xlim(lo - span * 0.20, hi + span * 0.28)
    ax.grid(True, axis="x", color=GRID, linewidth=0.5)
    ax.grid(False, axis="y")
    ax.set_axisbelow(True)
    ax.set_xlabel("平均客单价（R$）", fontsize=10, color=TXT)
    ax.legend(loc="lower right", fontsize=9.5)

    n_up = int((dlt > 0).sum())
    best, worst = dlt.idxmax(), dlt.idxmin()
    if n_up == len(dlt):
        title = f"四个最大州客单价全线上涨，{best} 涨幅最高 {dlt[best] * 100:+.1f}%"
    else:
        title = (f"四个最大州客单价分化：{n_up} 升 {len(dlt) - n_up} 降，"
                 f"{best} {dlt[best] * 100:+.1f}%／{worst} {dlt[worst] * 100:+.1f}%")

    frame(fig, ax, title,
          "两期均取 1-8 月等长窗口；连线长度即绝对差额",
          "模板 30｜对比滑珠图　数据源：orders_clean.csv　客单价 = 支付金额 ÷ 订单数（含运费）　"
          "右侧百分比为名义增幅（未剔除通胀）",
          top=0.82, bottom=0.21, left=0.08, right=0.96)
    save(fig, "fig11_dumbbell.png")


# =============================================================================
# 模块 4：主流程
# =============================================================================

TASKS = {
    "01": ("渐变柱形图", fig_01_gradient_bar),
    "02": ("带平均线柱形图", fig_02_avg_line_bar),
    "05": ("层叠柱形图", fig_05_stacked_bar),
    "11": ("平滑折线图", fig_11_smooth_line),
    "13": ("对比折线图", fig_13_compare_line),
    "14": ("单值圆环图", fig_14_donut),
    "17": ("玉玦图", fig_17_jade_ring),
    "23": ("柱形折线图", fig_23_bar_line),
    "26": ("柱形圆图", fig_26_bar_dot),
    "29": ("滑珠图", fig_29_slider_dot),
    "30": ("对比滑珠图", fig_30_dumbbell),
}

NEEDS = {
    "01": "orders", "02": "abc", "05": "orders", "11": "orders",
    "13": "orders", "14": "rfm", "17": "abc", "23": "orders",
    "26": "orders", "29": "orders", "30": "orders",
}


def main() -> int:
    ap = argparse.ArgumentParser(description="复现《Excel 数据可视化》11 种图表模板")
    ap.add_argument("--only", nargs="*", default=None,
                    help="只重画指定模板编号，例如 --only 05 17；缺省则全画")
    args = ap.parse_args()

    setup_style()
    codes = [c for c in TASKS if (args.only is None or c in args.only)]
    if not codes:
        log(f"[错误] 未匹配到任何模板编号，可选：{list(TASKS)}")
        return 1

    log(f"[计划] 待生成 {len(codes)} 张：{', '.join(f'{c}｜{TASKS[c][0]}' for c in codes)}")

    need = {NEEDS[c] for c in codes}
    ctx = {
        "orders": load_orders() if "orders" in need else None,
        "abc": load_abc() if "abc" in need else None,
        "rfm": load_rfm() if "rfm" in need else None,
    }

    log("\n[生成]")
    for c in codes:
        name, fn = TASKS[c]
        log(f"  {c}｜{name}")
        fn(ctx[NEEDS[c]])

    log(f"\n[完成] 共 {len(codes)} 张，输出目录 {FIG_DIR}")
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"repro_{stamp}.log"
    log_path.write_text("\n".join(_LOG_LINES) + "\n", encoding="utf-8")
    print(f"[日志] {log_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
