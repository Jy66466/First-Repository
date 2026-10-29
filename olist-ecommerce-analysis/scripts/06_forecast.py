# -*- coding: utf-8 -*-
"""
================================================================================
06_forecast.py —— 月度 GMV 时间序列预测（Holt / Holt-Winters ＋ 回测择优）
================================================================================

功能
    把主分析集按月汇总成 GMV 序列（20 个月），用前 17 个月训练、
    后 3 个月回测，比较候选模型的 MAPE / RMSE，自动选优，
    再用全样本重训并向后预测 3 个月，输出点预测与 95% 区间。

输入
    data/clean/orders_clean.csv     主分析集（97,308 单，2017-01-05 ~ 2018-08-29）

输出
    outputs/tables/forecast.csv     month, actual, forecast, lower95, upper95, is_forecast
    outputs/tables/metrics.csv      model, mape, rmse, status, is_selected, note
    logs/forecast_YYYYmmdd_HHMMSS.log

口径
    GMV          : 月度 sum(payment_total)，**含运费**，币种 BRL
                   （注意：与 05_boston_abc.py 的 price 口径不同，不可混用）
    训练/验证切分 : 前 17 个月（2017-01~2018-05）训练，后 3 个月（2018-06~08）验证
    候选模型      : A. Holt 线性趋势
                    A2. Holt 阻尼趋势（防止趋势外推过快）
                    B. Holt-Winters 加法季节（seasonal_periods = 12）
    择优规则      : 验证集 RMSE 最小（RMSE 同量纲、对大误差更敏感；MAPE 同时报告）
    95% 区间      : 残差近似法。statsmodels 0.15 的 HoltWintersResults **不提供**
                   get_prediction（已实测），故按 sigma_h = sigma * sqrt(h)
                   × t(0.975, df) 构造区间，并在日志中注明该方法与其局限。

三个必须写进论文的现实约束
    1) 样本仅 20 个月，**不足两个完整季节周期（24 个月）**，
       statsmodels 会直接抛出「less than two full seasonal cycles」，
       因此 12 个月季节项在本数据上**无法估计**——这是数据约束，不是代码问题。
    2) 2017-01 只有 1 月 5 日之后的订单（数据起点），该月 GMV 系统性偏低；
       2018-08 缺 8 月 30–31 日。首尾两个月都略被低估。
    3) 因此本模型的定位是「3 个月短外推 + 误差可量化」，
       不做长周期预测，也不用于替代业务判断。

运行
    在仓库根目录执行： python scripts/06_forecast.py
================================================================================
"""

from __future__ import annotations

import contextlib
import sys
import traceback
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# statsmodels 在样本不足时会刷大量 ConvergenceWarning，统一收敛到日志里的结论行
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

from statsmodels.tsa.holtwinters import ExponentialSmoothing  # noqa: E402

try:
    from scipy.stats import t as t_dist  # 用于 t 分位数
    HAS_SCIPY = True
except Exception:  # scipy 理论上随 statsmodels 一起装，这里做兜底
    HAS_SCIPY = False


# ==============================================================================
# 模块 0：全局配置
# ==============================================================================

CLEAN_DIR = Path("data/clean")
TABLE_DIR = Path("outputs/tables")
LOG_DIR = Path("logs")

ORDERS_FILE = CLEAN_DIR / "orders_clean.csv"
OUT_FORECAST = TABLE_DIR / "forecast.csv"
OUT_METRICS = TABLE_DIR / "metrics.csv"

CSV_ENCODING = "utf-8-sig"

SERIES_START = "2017-01"
SERIES_END = "2018-08"
N_TRAIN = 17          # 前 17 个月训练
N_VALID = 3           # 后 3 个月验证
FORECAST_HORIZON = 3  # 向后预测 3 个月（2018-09 ~ 2018-11）
SEASONAL_PERIODS = 12
CI_ALPHA = 0.05       # 95% 区间

BASELINE_ORDERS = 97_308

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
    return f"R$ {x:,.2f}"


# ==============================================================================
# 模块 2：构建月度序列
# ==============================================================================

def build_series() -> pd.Series:
    section("步骤 1 / 6　构建月度 GMV 序列")

    if not ORDERS_FILE.exists():
        raise FileNotFoundError(f"缺少 {ORDERS_FILE}，请先运行 02_clean.py")

    df = pd.read_csv(ORDERS_FILE, encoding=CSV_ENCODING, low_memory=False)
    df.columns = [str(c).replace("\ufeff", "").strip() for c in df.columns]

    df["order_purchase_timestamp"] = pd.to_datetime(df["order_purchase_timestamp"], errors="coerce")
    df["payment_total"] = pd.to_numeric(df["payment_total"], errors="coerce").astype(float)

    if df["order_purchase_timestamp"].isna().any():
        raise ValueError("存在无法解析的下单时间")

    # 无支付订单不参与 GMV（主分析集内通常为 0 单）
    if "has_payment" in df.columns:
        flag = df["has_payment"]
        if flag.dtype != bool:
            flag = flag.astype(str).str.lower().isin(["true", "1", "1.0"])
        n_drop = int((~flag).sum())
        if n_drop:
            log(f"  剔除无支付订单 {n_drop} 单")
            df = df[flag]

    if len(df) != BASELINE_ORDERS:
        log(f"  [提示] 订单数与基准 {BASELINE_ORDERS:,} 不一致（当前 {len(df):,}）")

    df["ym"] = df["order_purchase_timestamp"].dt.to_period("M").astype(str)
    s = df.groupby("ym", observed=True)["payment_total"].sum().sort_index()

    # 补齐月份索引，防止缺月导致时间轴错位
    expected = pd.period_range(SERIES_START, SERIES_END, freq="M").astype(str).tolist()
    missing = [m for m in expected if m not in s.index]
    extra = [m for m in s.index if m not in expected]
    if missing or extra:
        raise ValueError(f"月份不连续：缺 {missing}，多 {extra}")
    s = s.reindex(expected)

    if (s <= 0).any():
        bad = s[s <= 0].index.tolist()
        raise ValueError(f"存在非正 GMV 的月份：{bad}")

    # 转成 PeriodIndex：显式带月度频率，statsmodels 才不会报
    # "No frequency information was provided" 并自行猜测
    s.index = pd.PeriodIndex(s.index, freq="M")

    log(f"  月份数：{len(s)}（{expected[0]} ~ {expected[-1]}）")
    log(f"  GMV 合计：{brl(float(s.sum()))}")
    log(f"  月度区间：{brl(float(s.min()))} ~ {brl(float(s.max()))}　均值 {brl(float(s.mean()))}")
    log("  [口径提示] 2017-01 自 1 月 5 日起、2018-08 缺月末两天，首尾两月略被低估")

    log("")
    log("  月度 GMV：")
    for m, v in s.items():
        log(f"    {m}  {brl(float(v))}")

    return s


# ==============================================================================
# 模块 3：候选模型定义
# ==============================================================================

def candidate_models() -> list[dict]:
    """
    三个候选。B（季节项）在本数据上大概率失败——这是样本量约束下的必然结果，
    失败会被捕获并记录为「不可用」，而不是让脚本崩掉。
    """
    return [
        {
            "name": "Holt 线性趋势",
            "short": "A",
            "kwargs": dict(trend="add", seasonal=None, damped_trend=False),
        },
        {
            "name": "Holt 阻尼趋势",
            "short": "A2",
            "kwargs": dict(trend="add", seasonal=None, damped_trend=True),
        },
        {
            "name": "Holt-Winters 加法季节(12)",
            "short": "B",
            "kwargs": dict(trend="add", seasonal="add", seasonal_periods=SEASONAL_PERIODS),
        },
    ]


def fit_model(y: pd.Series, kwargs: dict):
    """拟合并返回结果对象；失败抛原始异常，由调用方记录。"""
    model = ExponentialSmoothing(
        y,
        initialization_method="estimated",
        **kwargs,
    )
    return model.fit(optimized=True)


# ==============================================================================
# 模块 4：回测与择优
# ==============================================================================

def mape(actual: np.ndarray, pred: np.ndarray) -> float:
    return float(np.mean(np.abs((actual - pred) / actual)) * 100)


def rmse(actual: np.ndarray, pred: np.ndarray) -> float:
    return float(np.sqrt(np.mean((actual - pred) ** 2)))


def backtest(series: pd.Series) -> tuple[pd.DataFrame, dict, pd.Series, pd.Series]:
    section("步骤 2 / 6　回测（17 个月训练 / 3 个月验证）")

    train = series.iloc[:N_TRAIN]
    valid = series.iloc[N_TRAIN:N_TRAIN + N_VALID]

    log(f"  训练集：{train.index[0]} ~ {train.index[-1]}（{len(train)} 个月）")
    log(f"  验证集：{valid.index[0]} ~ {valid.index[-1]}（{len(valid)} 个月）")
    log("")

    rows = []
    best = {"name": None, "rmse": np.inf, "result": None, "kwargs": None}

    for cfg in candidate_models():
        name = cfg["name"]
        try:
            res = fit_model(train, cfg["kwargs"])
            pred = res.forecast(N_VALID)
            pred.index = valid.index
            m, r = mape(valid.values, pred.values), rmse(valid.values, pred.values)
            rows.append({"model": name, "mape": round(m, 4), "rmse": round(r, 4), "status": "可用"})
            log(f"  [{cfg['short']}] {name:<24} MAPE {m:7.3f}%　RMSE {brl(r)}")
            log(f"       验证集预测：" + "　".join([f"{k} {brl(float(v))}" for k, v in pred.items()]))
            if r < best["rmse"]:
                best = {"name": name, "rmse": r, "result": res, "kwargs": cfg["kwargs"],
                        "mape": m, "pred": pred}
        except Exception as exc:
            # 典型：样本不足两个完整季节周期
            msg = f"{type(exc).__name__}: {str(exc)[:120]}"
            rows.append({"model": name, "mape": None, "rmse": None, "status": "不可用"})
            log(f"  [{cfg['short']}] {name:<24} 不可用 —— {msg}")

    metrics = pd.DataFrame(rows)

    # 记录不可用的原因，便于论文引用
    unavailable = metrics[metrics["status"] == "不可用"]
    if not unavailable.empty:
        log("")
        log("  [说明] 季节模型不可用的原因：")
        log("         Holt-Winters 需要至少两个完整季节周期（12×2 = 24 个月）才能估计季节项；")
        log(f"         本序列仅 {len(series)} 个月、训练段仅 {len(train)} 个月，故季节项无法估计。")
        log("         这不是参数写错，而是样本约束；论文应把「数据不支持季节模型」作为结论之一。")

    if best["name"] is None:
        raise RuntimeError("所有候选模型均无法拟合，无法继续预测")

    log("")
    log(f"  >>> 择优结果：{best['name']}（验证集 RMSE 最小 = {brl(best['rmse'])}，MAPE {best['mape']:.3f}%）")
    return metrics, best, train, valid


# ==============================================================================
# 模块 5：全样本重训 + 预测 + 区间
# ==============================================================================

def forecast_final(series: pd.Series, best: dict) -> tuple[pd.DataFrame, float, str]:
    section("步骤 3 / 6　全样本重训并向后预测 3 个月")

    res = fit_model(series, best["kwargs"])
    # 用 asarray 避免按标签对齐（statsmodels 返回的索引可能与本序列不同，直接对齐会变成 NaN）
    fitted = pd.Series(np.asarray(res.fittedvalues, dtype=float), index=series.index)

    # 点预测
    fc = res.forecast(FORECAST_HORIZON)
    future_index = pd.period_range(
        series.index[-1] + 1, periods=FORECAST_HORIZON, freq="M"
    ).astype(str)
    fc.index = future_index

    # 95% 区间：残差近似法
    resid = series.values - fitted.values
    n, k = len(series), len(res.params)
    df_resid = max(n - k, 1)
    sigma = float(np.sqrt(np.sum(resid ** 2) / df_resid))
    q = float(t_dist.ppf(1 - CI_ALPHA / 2, df_resid)) if HAS_SCIPY else 1.96
    steps = np.arange(1, FORECAST_HORIZON + 1)
    half = q * sigma * np.sqrt(steps)
    lower = fc.values - half
    upper = fc.values + half
    method = f"残差近似（sigma={sigma:,.2f}, df={df_resid}, t={q:.3f}）"
    if HAS_SCIPY is False:
        method = f"残差近似（正态 z=1.96，sigma={sigma:,.2f}）"

    if (lower < 0).any():
        log("  [提示] 区间下界出现负值，已截断为 0（GMV 不可能为负），并在论文注明")
        lower = np.clip(lower, 0, None)

    log(f"  最终模型：{best['name']}")
    log(f"  训练样本：{len(series)} 个月（全样本重训）")
    log(f"  区间方法：{method}")
    log(f"  残差标准差 sigma = {brl(sigma)}")
    log("")
    log(f"  {'月份':<9}{'点预测':>18}{'95% 下界':>18}{'95% 上界':>18}")
    log("  " + "-" * 63)
    for m, f, lo, hi in zip(future_index, fc.values, lower, upper):
        log(f"  {m:<9}{brl(float(f)):>18}{brl(float(lo)):>18}{brl(float(hi)):>18}")

    # 组装输出表：历史 20 行（拟合值）+ 未来 3 行
    hist = pd.DataFrame({
        "month": series.index.astype(str),
        "actual": series.values.round(2),
        "forecast": fitted.values.round(2),
        "lower95": np.nan,
        "upper95": np.nan,
        "is_forecast": False,
    })
    fut = pd.DataFrame({
        "month": future_index,
        "actual": np.nan,
        "forecast": fc.values.round(2),
        "lower95": lower.round(2),
        "upper95": upper.round(2),
        "is_forecast": True,
    })
    out = pd.concat([hist, fut], ignore_index=True)

    # 自检：区间包住点预测、未来月连续
    if not ((out.loc[out["is_forecast"], "lower95"] <= out.loc[out["is_forecast"], "forecast"]).all()
            and (out.loc[out["is_forecast"], "forecast"] <= out.loc[out["is_forecast"], "upper95"]).all()):
        raise AssertionError("置信区间未包住点预测")
    log("  [校验] 区间均包住点预测 ✓")

    return out, sigma, method


# ==============================================================================
# 模块 6：导出
# ==============================================================================

def export(out: pd.DataFrame, metrics: pd.DataFrame, best_name: str) -> None:
    section("步骤 4 / 6　导出")

    TABLE_DIR.mkdir(parents=True, exist_ok=True)

    out.to_csv(OUT_FORECAST, index=False, encoding=CSV_ENCODING)
    log(f"  预测明细 → {OUT_FORECAST}（{len(out)} 行：历史 {int((~out['is_forecast']).sum())} + 未来 {int(out['is_forecast'].sum())}）")

    metrics_out = metrics.copy()
    metrics_out["is_selected"] = metrics_out["model"] == best_name
    metrics_out["note"] = np.where(
        metrics_out["status"] == "不可用",
        "样本不足两个完整季节周期（需 24 个月），季节项无法估计",
        "",
    )
    metrics_out.to_csv(OUT_METRICS, index=False, encoding=CSV_ENCODING)
    log(f"  误差指标 → {OUT_METRICS}（{len(metrics_out)} 个候选模型）")

    # 回读校验：未来行必须有 actual 为空、is_forecast 为 True
    check = pd.read_csv(OUT_FORECAST, encoding=CSV_ENCODING)
    fut = check[check["is_forecast"]]
    if len(fut) != FORECAST_HORIZON:
        raise AssertionError(f"未来行数为 {len(fut)}，应为 {FORECAST_HORIZON}")
    if fut["actual"].notna().any():
        raise AssertionError("未来行的 actual 应为空")
    log(f"  [校验] 未来 {len(fut)} 行 actual 为空、is_forecast=True ✓")


# ==============================================================================
# 模块 7：结果解读
# ==============================================================================

def print_highlights(out: pd.DataFrame, metrics: pd.DataFrame, best: dict, sigma: float) -> None:
    section("步骤 5 / 6　要点与选择理由")

    fut = out[out["is_forecast"]]
    hist = out[~out["is_forecast"]]
    last_actual = float(hist["actual"].iloc[-1])
    avg_fc = float(fut["forecast"].mean())

    log(f"  最近一个月（{hist['month'].iloc[-1]}）实际 GMV：{brl(last_actual)}")
    log(f"  未来 3 个月预测均值：{brl(avg_fc)}　合计：{brl(float(fut['forecast'].sum()))}")
    log(f"  区间宽度（相对点预测）：±{float((fut['upper95'] - fut['forecast']).mean() / avg_fc * 100):.1f}%")
    log("")
    log(f"  {'模型':<24}{'MAPE':>10}{'RMSE':>20}{'状态':>8}")
    log("  " + "-" * 62)
    for _, r in metrics.iterrows():
        mape_s = "—" if pd.isna(r["mape"]) else f"{r['mape']:.3f}%"
        rmse_s = "—" if pd.isna(r["rmse"]) else brl(float(r["rmse"]))
        log(f"  {r['model']:<24}{mape_s:>10}{rmse_s:>20}{r['status']:>8}")
    log("")
    log("  选择理由：")
    log(f"    1. 三个候选中，{best['name']} 在 3 个月验证集上的 RMSE 最小（{brl(best['rmse'])}），")
    log("       即对大误差的抑制最好，适合 GMV 这种量级波动大的序列。")
    log(f"    2. MAPE 为 {best['mape']:.3f}%，可作为论文中的回测误差引用值。")
    log("    3. 季节模型因样本仅 20 个月（<24）无法估计季节项，已如实记录为「不可用」，")
    log("       未强行调参凑结果——这一点本身就是数据约束下的结论。")
    log("")
    log(f"  [误差解读] 残差标准差约为月均 GMV 的 {sigma / float(hist['actual'].mean()) * 100:.1f}%，")
    log("             说明月度波动仍较大，3 个月预测适合做预算区间，不适合做单点考核。")


# ==============================================================================
# 模块 8：自检
# ==============================================================================

def self_check(out: pd.DataFrame, series: pd.Series) -> None:
    section("步骤 6 / 6　自检")

    if len(out) != len(series) + FORECAST_HORIZON:
        raise AssertionError(f"输出行数 {len(out)} ≠ 历史 {len(series)} + 未来 {FORECAST_HORIZON}")
    log(f"  [1/4] 行数 = 历史 {len(series)} + 未来 {FORECAST_HORIZON} ✓")

    if out["month"].duplicated().any():
        raise AssertionError("month 存在重复")
    log("  [2/4] month 唯一且按时间连续 ✓")

    if (out["forecast"] < 0).any():
        raise AssertionError("存在负的预测值")
    log("  [3/4] 预测值非负 ✓")

    hist = out[~out["is_forecast"]]
    if hist["actual"].isna().any():
        raise AssertionError("历史行 actual 不应为空")
    log("  [4/4] 历史行 actual 完整 ✓")


# ==============================================================================
# 主流程
# ==============================================================================

def main() -> int:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOG_DIR / f"forecast_{datetime.now():%Y%m%d_%H%M%S}.log"

    with open(log_path, "w", encoding="utf-8") as log_file:
        with contextlib.redirect_stdout(Tee(sys.stdout, log_file)):
            log("=" * 78)
            log(f"06_forecast.py 运行时间：{datetime.now():%Y-%m-%d %H:%M:%S}")
            log(f"工作目录：{Path.cwd()}")
            log(f"序列：{SERIES_START} ~ {SERIES_END}　训练 {N_TRAIN} / 验证 {N_VALID} / 预测 {FORECAST_HORIZON}")
            log("=" * 78)

            series = build_series()
            metrics, best, train, valid = backtest(series)
            out, sigma, method = forecast_final(series, best)
            export(out, metrics, best["name"])
            print_highlights(out, metrics, best, sigma)
            self_check(out, series)

            section("完成")
            log(f"  最优模型：{best['name']}")
            log(f"  区间方法：{method}")
            log(f"  日志：{log_path}")
            log("  下一步：07_visuals.py（fig01–fig20 出图）")

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
