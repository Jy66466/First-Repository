# -*- coding: utf-8 -*-
"""
================================================================================
08_dashboard.py —— Olist 商业分析交互式大屏（Streamlit + Plotly）
================================================================================

运行方式（在仓库根目录执行）
    streamlit run scripts/08_dashboard.py
    默认地址 http://localhost:8501

依赖
    streamlit >= 1.49（用到 plotly_chart 的 on_select 点击回调与 width="stretch"）
    plotly、pandas

数据源（只读 outputs/tables 与 data/clean 的现成结果，不重算任何模型）
    data/clean/orders_clean.csv      订单主表（时间、州、客户、支付金额）
    data/clean/items_clean.csv       订单项明细（品类、商品金额）
    data/clean/customers_clean.csv   客户维表（州、经纬度）
    outputs/tables/rfm.csv           RFM 客户分群结果

六个组件
    ① 全局筛选器（侧边栏：时间范围 / 品类 / 州）
    ② KPI 卡片 ×4（GMV、订单数、客户数、客单价）
    ③ 月度 GMV 趋势（折线）
    ④ 品类结构 Top 8 + 其余合计（环形）
    ⑤ 巴西各州销售分布（散点地图，可点击下钻）
    ⑥ RFM 客户分群（散点）＋ 品类销售明细表（Top N）

口径说明（重要）
    大屏 GMV = items_clean 与 orders_clean 内连接后的 price 汇总
    （商品金额、不含运费）。全量筛选下等于 R$ 13,330,627.12，
    与 05_boston_abc.py 的品类 GMV 合计完全一致，可直接互相引用。
    对照：items_clean 单独全量求和是 R$ 13,591,643.70，其中含 2016 年与已取消
    订单的 1,358 单明细，不属主分析集，任何模型都不用它。
    另：RFM 的 M 与预测图的 payment_total（含运费）是另一套口径，不可混用。

联动说明
    时间/品类/州 → KPI、趋势、结构、地图、明细表全部实时响应。
    RFM 图不重算模型，只把「当前筛选范围内的客户」筛出来展示（R/F/M 仍是全窗口口径）。
    地图点击州 → 自动把州筛选器切到该州并重跑（若浏览器端选中事件不可用，用侧边栏下拉即可）。
================================================================================
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ------------------------------------------------------------------------------
# 全局配置
# ------------------------------------------------------------------------------

DATA_DIR = Path("data/clean")
TABLE_DIR = Path("outputs/tables")

CSV_ENCODING = "utf-8-sig"
JITTER_SEED = 42

# ---- 配色：全部取自 refs/color_palette.json，本文件不出现任何色值字面量 ----
# 与 07_visuals.py 同源，保证大屏截图（图 21）与静态图（图 1–20）配色一致。


def _palette_dir() -> Path:
    """定位 refs/color_palette.json：环境变量优先，其次仓库内外常见位置。"""
    here = Path(__file__).resolve()
    for c in (os.environ.get("PALETTE_DIR"),
              Path.cwd() / "refs", Path.cwd().parent / "refs",
              here.parent / "refs", here.parents[1] / "refs", here.parents[2] / "refs"):
        if c and (Path(c) / "color_palette.json").exists():
            return Path(c)
    raise FileNotFoundError("未找到 refs/color_palette.json；请设置环境变量 PALETTE_DIR")


sys.path.insert(0, str(_palette_dir()))
from palette import nu, pal  # noqa: E402

# R7：一张图只用一套色板；R5：文字/网格/参考线只走 neutrals
CAT = pal("categorical")   # 8 槽：主色 1–6 + 灰槽（其他/残差） + 辅色（浅）
SEQ = pal("sequential")    # 7 阶，明度单调，用于热力/色阶

TXT = nu("text")           # 文字
GRID = nu("grid")          # 网格线 / 卡片描边
AXIS = nu("axis_line")     # 轴线 / 强调描边
BG = nu("background")      # 画布白


def rgba(hexv: str, alpha: float) -> str:
    """把 palette 的 HEX 转成 Plotly 需要的 rgba()，透明度变化不算引入新色相。"""
    h = hexv.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"


# RFM 八分群配色：与 07_visuals.py 的 fig01_rfm_bubble 逐槽一致，
# 保证论文图 1 与大屏图 21 的同一分群是同一个颜色。
SEGMENT_COLORS = {
    "重要发展客户": CAT[0],
    "重要挽留客户": CAT[1],
    "一般挽留客户": CAT[2],
    "一般发展客户": CAT[3],
    "重要价值客户": CAT[4],
    "重要保持客户": CAT[5],
    "一般价值客户": CAT[7],
    "一般保持客户": CAT[6],   # 灰槽：最小类（168 户 / 0.18%）
}

# 地图色阶：7 阶顺序板 → Plotly colorscale（浅→深 = 低→高）
MAP_SCALE = [[i / (len(SEQ) - 1), h] for i, h in enumerate(SEQ)]

PLOTLY_FONT = dict(family="Microsoft YaHei, SimHei, sans-serif", size=12, color=TXT)
CHART_HEIGHT = 380

# 本地 topojson 底图：放在 scripts/static/topojson/un/ 下，
# 通过 Streamlit 的 /app/static 同源静态路由访问，避免运行时依赖 cdn.plot.ly。
TOPOJSON_URL = "app/static/topojson/un/"
TOPOJSON_PATH = Path(__file__).resolve().parent / "static" / "topojson" / "un" / "south-america_110m.json"

st.set_page_config(
    page_title="Olist 商业分析大屏",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ------------------------------------------------------------------------------
# 兼容层：新版 Streamlit 用 width="stretch"，旧版回退到 use_container_width
# ------------------------------------------------------------------------------

def wide_plotly(fig, **kwargs):
    try:
        return st.plotly_chart(fig, width="stretch", **kwargs)
    except TypeError:
        kwargs.pop("width", None)
        return st.plotly_chart(fig, use_container_width=True, **kwargs)


def wide_table(df, **kwargs):
    try:
        return st.dataframe(df, width="stretch", **kwargs)
    except TypeError:
        kwargs.pop("width", None)
        return st.dataframe(df, use_container_width=True, **kwargs)


# ------------------------------------------------------------------------------
# 数据加载（带缓存，避免每次交互重读大文件）
# ------------------------------------------------------------------------------

def _read_csv(path: Path, usecols=None) -> pd.DataFrame:
    if not path.exists():
        st.error(f"缺少数据文件：{path}，请先运行对应的模型脚本。")
        st.stop()
    df = pd.read_csv(path, encoding=CSV_ENCODING, usecols=usecols, low_memory=False)
    df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]
    return df


@st.cache_data(show_spinner="加载订单主表…")
def load_orders() -> pd.DataFrame:
    df = _read_csv(DATA_DIR / "orders_clean.csv",
                   usecols=lambda c: c in {"order_id", "customer_unique_id", "purchase_ym",
                                           "customer_state", "payment_total", "item_cnt"})
    df["purchase_ym"] = df["purchase_ym"].astype(str)
    df["payment_total"] = pd.to_numeric(df["payment_total"], errors="coerce").fillna(0.0)
    return df


@st.cache_data(show_spinner="加载订单明细…")
def load_items() -> pd.DataFrame:
    df = _read_csv(DATA_DIR / "items_clean.csv",
                   usecols=lambda c: c in {"order_id", "product_category_en", "price", "purchase_ym"})
    df["purchase_ym"] = df["purchase_ym"].astype(str)
    df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0.0)
    df["product_category_en"] = df["product_category_en"].fillna("unknown").astype(str)
    return df


@st.cache_data(show_spinner="加载客户维表…")
def load_customers() -> pd.DataFrame:
    df = _read_csv(DATA_DIR / "customers_clean.csv",
                   usecols=lambda c: c in {"customer_unique_id", "customer_state", "lat", "lng"})
    return df.dropna(subset=["lat", "lng"])


@st.cache_data(show_spinner="加载 RFM 结果…")
def load_rfm() -> pd.DataFrame:
    df = _read_csv(TABLE_DIR / "rfm.csv",
                   usecols=lambda c: c in {"customer_unique_id", "R", "F", "M", "Segment"})
    return df


# ------------------------------------------------------------------------------
# 工具函数
# ------------------------------------------------------------------------------

def money(x: float) -> str:
    """BRL 金额简写：百万/千，避免 KPI 卡数字过长。"""
    if x >= 1e6:
        return f"R$ {x / 1e6:,.2f}M"
    if x >= 1e3:
        return f"R$ {x / 1e3:,.1f}K"
    return f"R$ {x:,.0f}"


def style_fig(fig: go.Figure, title: str = "", height: int = CHART_HEIGHT) -> go.Figure:
    """
    统一图表风格：白底、细网格、无外框。
    关键：显式固定 template 与文字颜色。否则深色主题下 Plotly 会把图例文字和
    坐标轴刻度设成浅色，落在白色图例框上就是「白字白底」，看起来像图例丢了。
    """
    fig.update_layout(
        template="plotly_white",
        title=dict(text=title, x=0.01, xanchor="left", font=dict(size=15, color=TXT)),
        height=height,
        margin=dict(l=10, r=10, t=48, b=10),
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        font=PLOTLY_FONT,
        hoverlabel=dict(bgcolor=BG, bordercolor=GRID,
                        font=dict(family="Microsoft YaHei", size=12, color=TXT)),
        legend=dict(bgcolor=rgba(BG, 0.95), bordercolor=GRID, borderwidth=1,
                    font=dict(color=TXT, size=10)),
    )
    fig.update_xaxes(showgrid=False, linecolor=AXIS,
                     tickfont=dict(color=TXT), title_font=dict(color=TXT))
    fig.update_yaxes(showgrid=True, gridcolor=rgba(GRID, 0.6), linecolor=AXIS,
                     tickfont=dict(color=TXT), title_font=dict(color=TXT))
    return fig


# ------------------------------------------------------------------------------
# 侧边栏：全局筛选器
# ------------------------------------------------------------------------------

def sidebar_filters(orders: pd.DataFrame, items: pd.DataFrame) -> tuple[str, str, list[str], str]:
    # 用 Markdown 标题而非内联颜色：让 Streamlit 按当前主题自动取色，
    # 深色主题下不会再出现「深蓝字压在深色底上」的低对比问题
    st.sidebar.markdown("## 📊 Olist 商业分析")
    st.sidebar.caption("Brazilian E-Commerce · 2017-01 ~ 2018-08")
    st.sidebar.markdown("---")

    # ① 时间范围（按年月）
    months = sorted(orders["purchase_ym"].dropna().unique().tolist())
    if not months:
        st.error("订单表没有可用的 purchase_ym")
        st.stop()
    start, end = st.sidebar.select_slider(
        "① 时间范围（下单年月）",
        options=months,
        value=(months[0], months[-1]),
        help="拖动两端选择区间；所有组件随区间实时变化",
    )

    # ② 品类
    cats = sorted(items["product_category_en"].dropna().unique().tolist())
    picked_cats = st.sidebar.multiselect(
        "② 品类（可多选，留空 = 全部）",
        options=cats,
        default=[],
        help="选择后 GMV 只统计所选品类；留空表示全部品类",
    )

    # ③ 州（地图点击会同步到这里）
    states = sorted(orders["customer_state"].dropna().unique().tolist())
    states = [s for s in states if s and s != "unknown"]
    state_sel = st.sidebar.selectbox(
        "③ 州（点地图也可切换）",
        options=["全部"] + states,
        key="state_filter",
        on_change=lambda: st.session_state.pop("last_map_click", None),
        help="选择某个州后，趋势图/明细表/地图都会收窄到该州；手动切换后可重新点地图",
    )

    st.sidebar.markdown("---")
    st.sidebar.caption(
        "口径：GMV = 商品金额（price），不含运费。\n\n"
        "RFM 的 M 与预测图用的是支付金额（含运费），两者不可直接对比。"
    )
    return start, end, picked_cats, state_sel


# ------------------------------------------------------------------------------
# 数据过滤（所有组件共用这一份结果，保证口径一致）
# ------------------------------------------------------------------------------

def apply_filters(orders, items, start, end, cats, state_sel):
    o = orders[(orders["purchase_ym"] >= start) & (orders["purchase_ym"] <= end)]
    it = items[(items["purchase_ym"] >= start) & (items["purchase_ym"] <= end)]

    if state_sel != "全部":
        o = o[o["customer_state"] == state_sel]

    if cats:
        it = it[it["product_category_en"].isin(cats)]
        valid_ids = set(it["order_id"]).intersection(set(o["order_id"]))
        o = o[o["order_id"].isin(valid_ids)]
        it = it[it["order_id"].isin(valid_ids)]
    else:
        # 未选品类：以订单表为准，明细只保留这些订单
        it = it[it["order_id"].isin(set(o["order_id"]))]

    return o, it


# ------------------------------------------------------------------------------
# 组件
# ------------------------------------------------------------------------------

def render_kpis(o: pd.DataFrame, it: pd.DataFrame) -> None:
    gmv = float(it["price"].sum())
    n_orders = int(o["order_id"].nunique())
    n_cust = int(o["customer_unique_id"].nunique())
    aov = gmv / n_orders if n_orders else 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("总 GMV（商品金额）", money(gmv),
              help="items_clean ∩ orders_clean 的 price 合计，不含运费；与 ABC/波士顿模型同口径")
    c2.metric("订单数", f"{n_orders:,}", help="orders_clean 去重订单数")
    c3.metric("客户数", f"{n_cust:,}", help="customer_unique_id 去重数")
    c4.metric("客单价", f"R$ {aov:,.2f}",
              help="商品金额 ÷ 订单数；按支付金额（含运费）口径会更高，两者不可混用")


def render_trend(it: pd.DataFrame) -> go.Figure:
    g = it.groupby("purchase_ym", as_index=False)["price"].sum().sort_values("purchase_ym")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=g["purchase_ym"], y=g["price"], mode="lines+markers",
        line=dict(color=CAT[2], width=2.6), marker=dict(size=6, color=CAT[2]),
        fill="tozeroy", fillcolor=rgba(CAT[2], 0.12),
        hovertemplate="%{x}<br>GMV R$ %{y:,.0f}<extra></extra>",
        name="月度 GMV",
    ))
    fig.update_yaxes(tickformat=",.0f", title="GMV（R$）")
    fig.update_xaxes(title="")
    return style_fig(fig, "月度 GMV 趋势")


def render_category(it: pd.DataFrame) -> go.Figure:
    g = it.groupby("product_category_en", as_index=False)["price"].sum()
    g = g.sort_values("price", ascending=False)
    # 只取 Top 8：分类板共 8 槽（R7 一图一板），
    # 超过 8 片就无法保证 R1「两两 ΔE00 ≥ 20」，宁可把长尾并入「其余」。
    top = g.head(8).copy()
    rest = g["price"].iloc[8:].sum()
    if rest > 0:
        top = pd.concat([top, pd.DataFrame([{"product_category_en": "其余品类合计", "price": rest}])],
                        ignore_index=True)

    fig = go.Figure(go.Pie(
        labels=top["product_category_en"], values=top["price"], hole=0.55,
        # 前 8 片 = 分类板 8 槽；末片「其余」用中性灰（灰槽语义：残差，不参与比较）
        marker=dict(colors=(CAT + [GRID])[:len(top)],
                    line=dict(color=BG, width=1.5)),
        textinfo="percent", textposition="inside",
        hovertemplate="%{label}<br>R$ %{value:,.0f}（%{percent}）<extra></extra>",
        sort=False,
    ))
    fig = style_fig(fig, "品类结构 Top 8 + 其余")

    # 图例改回右侧竖排：英文品类名较长，横排在底部会被挤成两行、贴边。
    # domain 把饼图压到左侧 55%，右边 35% 留给图例，整体仍在卡片内居中。
    fig.update_traces(domain=dict(x=[0, 0.55]))
    fig.update_layout(
        showlegend=True,
        legend=dict(orientation="v", x=0.65, y=0.5, yanchor="middle",
                    font=dict(size=10)),
        margin=dict(l=6, r=6, t=48, b=16),
    )
    return fig


def render_map(o: pd.DataFrame, it: pd.DataFrame, customers: pd.DataFrame) -> go.Figure:
    # 订单级商品金额 → 按州汇总
    order_gmv = it.groupby("order_id", as_index=False)["price"].sum()
    od = o[["order_id", "customer_state"]].merge(order_gmv, on="order_id", how="left").fillna({"price": 0})
    by_state = od.groupby("customer_state", as_index=False)["price"].sum()

    # 州质心（客户维表经纬度均值），避免额外引入 geojson
    cent = customers.groupby("customer_state", as_index=False)[["lat", "lng"]].mean()
    m = by_state.merge(cent, on="customer_state", how="inner")
    m = m[m["price"] > 0].sort_values("price", ascending=False)

    if m.empty:
        fig = go.Figure()
        fig.add_annotation(text="当前筛选下没有可展示的州", showarrow=False, font=dict(size=14))
        return style_fig(fig, "各州销售分布")

    size = np.sqrt(m["price"] / m["price"].max()) * 42 + 6

    # 色阶改对数：SP 约 510 万、RR 约 0.76 万，相差三个数量级，
    # 线性色阶会让除 SP 外的州全部接近白色，看不出层次
    log_gmv = np.log10(m["price"].clip(lower=1))
    # 只给 Top 6 州打文字标签，其余靠 hover，避免东南部小州挤成一团
    labels = [st_ if i < 6 else "" for i, st_ in enumerate(m["customer_state"])]

    fig = go.Figure(go.Scattergeo(
        lon=m["lng"], lat=m["lat"], text=labels, hovertext=m["customer_state"],
        customdata=m["price"].values,
        mode="markers+text", textposition="top center",
        textfont=dict(size=9.5, color=TXT),
        marker=dict(size=size, color=log_gmv, colorscale=MAP_SCALE,
                    cmin=float(log_gmv.min()), cmax=float(log_gmv.max()),
                    line=dict(width=0.6, color=BG),
                    colorbar=dict(title="GMV<br>(R$)", thickness=12, len=0.62,
                                  tickvals=[3, 4, 5, 6],
                                  ticktext=["1K", "10K", "100K", "1M"])),
        hovertemplate="%{hovertext}<br>GMV R$ %{customdata:,.0f}<extra></extra>",
    ))
    fig.update_geos(
        scope="south america", showcountries=True, countrycolor=rgba(AXIS, 0.55),
        showland=True, landcolor=rgba(GRID, 0.25), showocean=True, oceancolor=BG,
        showframe=False, projection_type="mercator",
        lataxis_range=[-35, 6], lonaxis_range=[-75, -32],
    )
    fig = style_fig(fig, "各州销售分布（点大小 = GMV）", height=CHART_HEIGHT + 40)
    fig.update_layout(margin=dict(l=0, r=0, t=48, b=0))
    return fig


def render_rfm(rfm: pd.DataFrame, customers_in_scope: set) -> go.Figure:
    df = rfm[rfm["customer_unique_id"].isin(customers_in_scope)]
    rng = np.random.default_rng(JITTER_SEED)
    fig = go.Figure()

    # 按客户数降序绘制：大分群先画在底层，小分群后画在上层，
    # 否则 2 万+ 点的「重要发展/挽留」会被后绘制的分群整片盖住。
    # 图例顺序另用 legendrank 固定为「重要价值→…→一般挽留」的业务顺序，
    # 让「先画谁」和「先读谁」互不牵制。
    # 图例按「重要性 → 一般」的业务顺序读，不跟随绘制顺序
    LEGEND_ORDER = ["重要价值客户", "重要发展客户", "重要保持客户", "重要挽留客户",
                    "一般价值客户", "一般发展客户", "一般保持客户", "一般挽留客户"]
    rank = {seg: i for i, seg in enumerate(LEGEND_ORDER)}
    order = sorted([s for s in SEGMENT_COLORS if s in set(df["Segment"])],
                   key=lambda x: -(df["Segment"] == x).sum())
    for seg in order:
        sub = df[df["Segment"] == seg]
        if sub.empty:
            continue
        # y 加抖动只为把 F=1 的点摊开；hover 用原始 F，避免显示成「1.3 单」
        fig.add_trace(go.Scattergl(
            x=sub["R"], y=sub["F"] + rng.normal(0, 0.07, len(sub)),
            mode="markers", name=f"{seg}（{len(sub):,}）", legendrank=rank[seg],
            marker=dict(size=3.6, color=SEGMENT_COLORS[seg], opacity=0.55),
            customdata=np.stack([sub["M"].values, sub["F"].values], axis=-1),
            hovertemplate=("R %{x} 天<br>F %{customdata[1]:.0f} 单<br>"
                           "M R$ %{customdata[0]:,.0f}<br>" + seg + "<extra></extra>"),
        ))

    fig.update_xaxes(title="R：距最近一次购买天数")
    fig.update_yaxes(title="F：购买次数（已加抖动）")

    # 点出「F=1 占绝大多数」这个事实，否则一条横带容易被误读成绘图错误
    if not df.empty:
        f1 = int((df["F"] == 1).sum())
        fig.add_annotation(
            x=float(df["R"].median()), y=1.0,
            text=f"F=1 占 {(df['F'] == 1).mean() * 100:.1f}%（{f1:,} 户）",
            showarrow=True, arrowhead=2, ax=0, ay=-46,
            font=dict(size=10, color=TXT),
            bgcolor=rgba(BG, 0.92), bordercolor=AXIS, borderwidth=1,
        )

    fig = style_fig(fig, "RFM 客户分群（仅当前筛选客户）")
    fig.update_layout(legend=dict(font=dict(size=9), itemsizing="constant"))
    return fig


def render_table(o: pd.DataFrame, it: pd.DataFrame, top_n: int) -> pd.DataFrame:
    m = it[["order_id", "product_category_en", "price"]].merge(
        o[["order_id", "customer_unique_id"]], on="order_id", how="left")
    g = (m.groupby("product_category_en")
           .agg(GMV=("price", "sum"),
                订单数=("order_id", "nunique"),
                客户数=("customer_unique_id", "nunique"))
           .reset_index()
           .sort_values("GMV", ascending=False))
    total = g["GMV"].sum()
    g["GMV占比"] = g["GMV"] / total if total else 0
    g["累计占比"] = g["GMV占比"].cumsum()
    g = g.head(top_n)
    g["GMV"] = g["GMV"].round(2)
    g["GMV占比"] = (g["GMV占比"] * 100).round(2)
    g["累计占比"] = (g["累计占比"] * 100).round(2)
    g = g.rename(columns={"product_category_en": "品类"})
    return g.reset_index(drop=True)


# ------------------------------------------------------------------------------
# 主流程
# ------------------------------------------------------------------------------

def main() -> None:
    # 地图点击 → 同步到州筛选器：在创建下拉框之前先消费掉"待生效的州"
    if "pending_state" in st.session_state:
        st.session_state["state_filter"] = st.session_state.pop("pending_state")

    orders = load_orders()
    items = load_items()
    customers = load_customers()
    rfm = load_rfm()

    start, end, cats, state_sel = sidebar_filters(orders, items)

    o, it = apply_filters(orders, items, start, end, cats, state_sel)

    # 顶部标题栏
    left, right = st.columns([3, 1])
    with left:
        # st.title 会跟随主题取色，深色/浅色都不用改代码
        st.title("Olist 电商经营分析大屏")
        st.caption(f"筛选：{start} ~ {end}　|　品类：{'全部' if not cats else f'{len(cats)} 个'}　|　州：{state_sel}")
    with right:
        st.caption(f"数据窗口：{start} ~ {end}")

    if o.empty or it.empty:
        st.warning("当前筛选条件下没有数据，请放宽时间范围或清空品类/州筛选。")
        st.stop()

    # ② KPI
    render_kpis(o, it)
    st.markdown("")

    # ③④ 趋势 + 结构
    c1, c2 = st.columns([1.55, 1])
    with c1:
        wide_plotly(render_trend(it))
    with c2:
        wide_plotly(render_category(it))

    # ⑤ 地图 + ⑥ RFM
    c3, c4 = st.columns([1.25, 1])
    with c3:
        if not TOPOJSON_PATH.exists():
            st.warning(f"本地底图缺失：{TOPOJSON_PATH}")

        event = wide_plotly(
            render_map(o, it, customers),
            on_select="rerun",
            selection_mode="points",
            key="map_chart",
            config={"topojsonURL": TOPOJSON_URL},
        )
        # 点击州 → 下钻（用一个标记避免重复重跑）
        try:
            points = (event or {}).get("selection", {}).get("points", [])
        except Exception:
            points = []
        if points:
            raw = points[0].get("customdata", points[0].get("location"))
            clicked = raw[0] if isinstance(raw, (list, tuple)) else raw
            if clicked and clicked != st.session_state.get("last_map_click"):
                st.session_state["last_map_click"] = clicked
                if clicked != (None if state_sel == "全部" else state_sel):
                    st.session_state["pending_state"] = clicked
                    st.rerun()
    with c4:
        wide_plotly(render_rfm(rfm, set(o["customer_unique_id"])))
        st.caption("说明：RFM 的 R/F/M 为全窗口计算结果，此处只按当前筛选客户过滤展示，不重算模型。")

    # 明细表
    st.markdown("---")
    head, ctrl = st.columns([3, 1])
    with head:
        st.subheader("品类销售明细")
    with ctrl:
        top_n = st.slider("显示 Top N", min_value=5, max_value=30, value=10, step=5, label_visibility="collapsed")

    table = render_table(o, it, top_n)
    wide_table(
        table, hide_index=True,
        column_config={
            "GMV": st.column_config.NumberColumn("GMV（R$）", format="%.2f"),
            "GMV占比": st.column_config.NumberColumn("GMV 占比", format="%.2f%%"),
            "累计占比": st.column_config.NumberColumn("累计占比", format="%.2f%%"),
        },
    )

    scope = "all" if state_sel == "全部" else state_sel
    cat_tag = "all" if not cats else f"{len(cats)}cats"
    st.caption(
        "注：订单数/客户数为**该品类内**的去重计数；一张订单含多个品类时会在各品类各计一次，"
        "因此各行之和大于总订单数。占比按品类 GMV 计算，与 KPI 卡口径一致。"
    )

    st.download_button(
        "⬇ 下载当前筛选的明细 CSV",
        data=table.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"olist_detail_{start}_{end}_{scope}_{cat_tag}.csv",
        mime="text/csv",
    )

    st.caption(
        "口径与来源：GMV = items_clean ∩ orders_clean 的 price 汇总（商品金额，不含运费，"
        "与 ABC/波士顿模型同口径，全量下 R$ 13,330,627.12）；订单/客户数取 orders_clean；"
        "RFM 来自 outputs/tables/rfm.csv；州坐标为 customers_clean 经纬度均值。"
    )


# Streamlit 每次交互都会自上而下重新执行本文件
main()
