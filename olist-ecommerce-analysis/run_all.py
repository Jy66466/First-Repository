# -*- coding: utf-8 -*-
"""
run_all.py —— 一键复现《Olist 电商客户分群与销售结构可视化分析》的全部结果

依次执行 7 个环节（清洗 → 4 个模型 → 2 组图表），任一步非零退出即中止。
交互式大屏（08_dashboard.py）是常驻 Web 服务，不放进流水线，末尾单独提示启动命令。

输入：data/raw/ 下 9 个原始 CSV（Kaggle 官方 CLI 下载，见 README）
输出：data/clean/*.csv、outputs/tables/*.csv、outputs/figures/fig01–fig20.png、logs/run_all_*.log

用法：
    python run_all.py                 # 全量跑
    python run_all.py --from 03       # 从 RFM 开始（前面结果已存在时省时间）
    python run_all.py --only 07 09    # 只重画两组图
    python run_all.py --profile       # 先跑一次数据核验（01_data_profiling.py）
    python run_all.py --list          # 只看步骤清单
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent
LOG_DIR = ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# (编号, 脚本相对路径, 说明, 主要产物)
STEPS = [
    ("02", "scripts/02_clean.py",       "数据清洗与治理",            "6 张 clean 表 + 全状态订单表"),
    ("03", "scripts/03_rfm.py",         "RFM 八分类",                "rfm.csv / rfm_summary.csv"),
    ("04", "scripts/04_cohort.py",      "同期群留存",                "cohort_size.csv / cohort_matrix.csv"),
    ("05", "scripts/05_boston_abc.py",  "帕累托-ABC + 波士顿矩阵",    "abc.csv / boston_matrix.csv / boston_meta.csv"),
    ("06", "scripts/06_forecast.py",    "Holt 阻尼趋势预测",          "forecast.csv / metrics.csv"),
    ("07", "scripts/07_visuals.py",     "图 12–图 20　业务模型图",     "fig12–fig20 *.png"),
    ("09", "scripts/09_visuals_repro.py", "图 1–图 11　模板复现图",     "fig01–fig11 *.png"),
]

RAW_FILES = [
    "olist_orders_dataset.csv",
    "olist_order_items_dataset.csv",
    "olist_order_payments_dataset.csv",
    "olist_order_reviews_dataset.csv",
    "olist_customers_dataset.csv",
    "olist_products_dataset.csv",
    "olist_sellers_dataset.csv",
    "olist_geolocation_dataset.csv",
    "product_category_name_translation.csv",
]


def say(msg: str = "") -> None:
    print(msg, flush=True)


def preflight() -> list[str]:
    """返回阻塞性问题清单；空列表表示可以开工。"""
    problems: list[str] = []
    if sys.version_info < (3, 10):
        problems.append(f"Python 版本过低：{sys.version.split()[0]}，需要 ≥ 3.10")

    raw = ROOT / "data" / "raw"
    missing = [f for f in RAW_FILES if not (raw / f).exists()]
    if missing:
        problems.append(f"data/raw 缺 {len(missing)} 个文件：{', '.join(missing[:3])}"
                        + ("…" if len(missing) > 3 else ""))

    absent = [s for _, s, _, _ in STEPS if not (ROOT / s).exists()]
    if absent:
        problems.append(f"缺少脚本：{', '.join(absent)}")

    try:
        import pandas, numpy, matplotlib  # noqa: F401
    except ImportError as e:
        problems.append(f"依赖缺失：{e.name}，请先 pip install -r requirements.txt")
    return problems


def run_step(code: str, script: str, desc: str) -> tuple[bool, float]:
    say(f"\n{'=' * 74}")
    say(f"[{code}] {desc}　→　{script}")
    say("=" * 74)
    t0 = time.time()
    proc = subprocess.run([sys.executable, script], cwd=ROOT)
    cost = time.time() - t0
    if proc.returncode != 0:
        say(f"[失败] {code} 退出码 {proc.returncode}，已中止后续步骤（耗时 {cost:.1f}s）")
        return False, cost
    say(f"[完成] {code}　耗时 {cost:.1f}s")
    return True, cost


def main() -> int:
    ap = argparse.ArgumentParser(description="一键复现全部清洗、建模与图表")
    ap.add_argument("--from", dest="start", default=None, help="从指定编号开始，如 03")
    ap.add_argument("--only", nargs="*", default=None, help="只跑指定编号，如 07 09")
    ap.add_argument("--profile", action="store_true", help="先跑一次数据核验")
    ap.add_argument("--list", action="store_true", help="只打印步骤清单")
    args = ap.parse_args()

    if args.list:
        say(f"{'编号':<6}{'说明':<26}{'主要产物'}")
        say("-" * 78)
        for code, script, desc, out in STEPS:
            say(f"{code:<6}{desc:<26}{out}")
        return 0

    say("=" * 78)
    say(f"run_all.py　{datetime.now():%Y-%m-%d %H:%M:%S}")
    say(f"工作目录：{ROOT}")
    say(f"Python：{sys.version.split()[0]}（{sys.executable}）")
    say("=" * 78)

    problems = preflight()
    if problems:
        say("\n[预检未通过]")
        for p in problems:
            say(f"  ✗ {p}")
        say("\n处理完上述问题后重新运行。")
        return 1
    say("[预检] 通过：9 个原始文件齐全，7 个脚本就位，核心依赖可导入")

    if args.profile:
        prof = ROOT / "tools" / "01_data_profiling.py"
        if prof.exists():
            say("\n[附加] 数据核验 01_data_profiling.py")
            subprocess.run([sys.executable, str(prof)], cwd=ROOT)

    todo = STEPS
    if args.only:
        todo = [s for s in STEPS if s[0] in args.only]
        if not todo:
            say(f"[错误] 未匹配编号：{args.only}，可选 {[s[0] for s in STEPS]}")
            return 1
    elif args.start:
        codes = [s[0] for s in STEPS]
        if args.start not in codes:
            say(f"[错误] 起始编号不存在：{args.start}，可选 {codes}")
            return 1
        todo = STEPS[codes.index(args.start):]

    results: list[tuple[str, str, bool, float]] = []
    total0 = time.time()
    for code, script, desc, _ in todo:
        ok, cost = run_step(code, script, desc)
        results.append((code, desc, ok, cost))
        if not ok:
            break

    elapsed = time.time() - total0
    say("\n" + "=" * 78)
    say("执行汇总")
    say("-" * 78)
    for code, desc, ok, cost in results:
        say(f"  {'[OK]' if ok else '[FAIL]'}  {code}  {desc:<26}{cost:>7.1f}s")
    say("-" * 78)
    say(f"总计 {len(results)} 步，成功 {sum(1 for r in results if r[2])} 步，"
        f"总耗时 {elapsed:.1f}s")
    say("=" * 78)

    if all(r[2] for r in results) and len(results) == len(todo):
        say("\n大屏不在本流水线内，需单独启动：")
        say("    streamlit run scripts/08_dashboard.py")
        say("浏览器打开 http://localhost:8501，截图存为 outputs/figures/fig21_dashboard.png")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"run_all_{stamp}.log"
    log_path.write_text(
        "\n".join(f"{'OK ' if r[2] else 'FAIL'} {r[0]} {r[1]} {r[3]:.1f}s" for r in results)
        + f"\nTOTAL {elapsed:.1f}s\n",
        encoding="utf-8",
    )
    say(f"日志：{log_path}")
    return 0 if all(r[2] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
