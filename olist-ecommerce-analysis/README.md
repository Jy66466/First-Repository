# Olist 电商客户分群与销售结构可视化分析

> 商业数据分析项目 · 独立完成
> 数据源：Kaggle **Brazilian E-Commerce Public Dataset by Olist**（CC BY-NC-SA 4.0）
> 全流程 Python 实现：清洗 → 5 个模型 → 21 张图 + 1 个交互大屏，无 Excel、无 BI 软件、无 Faker。

---

## 一、项目简介

以巴西电商平台 Olist 的 2017-01 ~ 2018-08 交易数据（主分析集 **97,308 单 / 94,136 位客户**）为对象，回答三个问题：客户价值如何分布、销售结构是否过度集中、现有增长能否延续。

**三条核心结论**

| # | 结论 | 关键证据 |
|---|---|---|
| 1 | 平台属**拉新驱动、留存失效** | 复购率仅 **3.03%**；**94.37%** 的 GMV 来自一次性客户；次月留存自 100% 断崖跌至 **0.49%** |
| 2 | 销售结构**高度集中** | 17 个 A 类品类（23.61%）贡献 **79.71%** 销售额；A 类前 8 个品类即占 50% |
| 3 | 增长动能**已现走弱迹象** | 金牛 18 个品类占 **52.72%** GMV 但跑输大盘（+140.63%）；Holt 阻尼趋势 MAPE **28.79%**，误差源于 2018 下半年趋势转弱 |

**一个必须说清的口径**：平台销售额存在两套口径——`payment_total`（支付金额，含运费，全量 R$ 15,551,539.96）与 `price`（商品金额，不含运费，全量 R$ 13,330,627.12）。模型用前者，品类结构用后者，两者**不可加减**。

---

## 二、五个分析模型

| 模型 | 脚本 | 核心产出 |
|---|---|---|
| RFM 八分类 | `03_rfm.py` | 94,136 位客户分 8 群；F 维按 1 单/≥2 单切分（因复购率过低，中位数恒为 1） |
| 同期群留存 | `04_cohort.py` | 18 个 cohort、81,945 户；首月断崖 + 长尾贴地 |
| 帕累托 / ABC | `05_boston_abc.py` | 72 个品类三级分类；含异常值敏感性检验（Spearman 0.9138） |
| 波士顿矩阵 | `05_boston_abc.py` | 品类份额 × 等长窗口增速；明星/金牛/问题/瘦狗 18/18/17/17，另有 2 个基期为 0 的未定品类（合计 72） |
| Holt 趋势预测 | `06_forecast.py` | 三模型回测择优（阻尼趋势），带 95% 区间与 MAPE/RMSE |

---

## 三、快速开始

### 1. 环境

```bat
cd /d <仓库根目录>
py -3.11 -m venv .venv
.venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Python ≥ 3.10；`requirements.txt` 不含版本锁，装完可 `pip freeze > requirements.lock.txt` 留档。

### 2. 取数（Kaggle 官方 CLI，不使用爬虫）

```bat
kaggle datasets download -d olistbr/brazilian-ecommerce -p data/raw --unzip
```

需先在 <https://www.kaggle.com/settings> 生成 API Token，放到 `%USERPROFILE%\.kaggle\kaggle.json`。
解压后 9 个 CSV **平铺**放在 `data/raw/`，不改名、不移动、不修改原文件。

### 3. 一键运行

```bat
python run_all.py              REM 全量：清洗 → 5 模型 → 20 张静态图
python run_all.py --profile    REM 先跑一次数据核验
python run_all.py --only 07 09 REM 只重画两组图
python run_all.py --list       REM 看步骤清单
```

任一步失败即中止并打印退出码，日志写入 `logs/run_all_*.log`。

### 4. 交互式大屏（单独启动）

```bat
streamlit run scripts/08_dashboard.py
```

浏览器打开 <http://localhost:8501>，截图存为 `outputs/figures/fig21_dashboard.png`。
大屏含 7 个联动组件：全局筛选器、KPI 卡、月度趋势、品类环形、州级散点地图、RFM 分群散点、销售明细。

---

## 四、目录结构

```
.
├── run_all.py                 一键复现
├── requirements.txt
├── README.md
├── LICENSE                    CC BY-NC-SA 4.0（适用于本项目代码与派生数据）
├── data/
│   ├── raw/                   9 个原始 CSV（不入库，需自行下载）
│   ├── clean/                 7 张清洗表 + LICENSE + SOURCE.md
│   └── schema.md              字段字典
├── scripts/
│   ├── 02_clean.py            清洗与治理
│   ├── 03_rfm.py              RFM 八分类
│   ├── 04_cohort.py           同期群留存
│   ├── 05_boston_abc.py       ABC + 波士顿矩阵 + 敏感性检验
│   ├── 06_forecast.py         时间序列预测
│   ├── 07_visuals.py          图 12–图 20
│   ├── 08_dashboard.py        交互式大屏（图 21）
│   └── 09_visuals_repro.py    图 1–图 11
├── tools/
│   ├── check_env.py           环境自检
│   └── 01_data_profiling.py   原始数据核验
├── outputs/
│   ├── figures/               fig01–fig21 *.png（150 dpi）
│   └── tables/                rfm / cohort / abc / boston / forecast 等结果表
├── docs/                      大屏操作说明、图表索引
└── logs/                      每次运行的完整日志
```

---

## 五、21 张图

| 组别 | 图号 | 内容 | 脚本 |
|---|---|---|---|
| 业务模型图（9） | 图 12–图 20 | RFM 气泡与贡献柱、留存热力与折线、波士顿四象限与象限分布、帕累托曲线、ABC 堆叠、预测区间 | `07_visuals.py` |
| 模板复现图（11） | 图 1–图 11 | 渐变柱、平均线柱、层叠柱、平滑折线、对比折线、单值圆环、玉玦、柱形折线、柱形圆、滑珠、对比滑珠 | `09_visuals_repro.py` |
| 交互大屏（1） | 图 21 | Streamlit 七组件联动看板 | `08_dashboard.py` |

模板复现对照原书《Excel 数据可视化——从图表到数据大屏》的 30 种模板，覆盖 **11 种不同模板**（01/02/05/11/13/14/17/23/26/29/30），逐图映射见 `docs/附录C_图表索引.md`。

---

## 六、合规与学术诚信

1. **数据获取**：仅通过 Kaggle 官方 CLI 下载，全程**未使用任何爬虫**，未修改 `data/raw/` 中的原始文件。
2. **数据真实性**：**未使用 Faker** 或任何工具生成、补足、替换记录；样本量完全由原始数据决定（清洗后主分析集 97,308 单，远超 ≥500 条的要求）。
3. **工具边界**：全部清洗、建模与出图由 Python 完成，**未使用 Power BI / Tableau 等 BI 软件出图**；Excel 仅用于结果核对，不参与作图。
4. **许可协议**：原始数据采用 **CC BY-NC-SA 4.0**（署名—非商业性使用—相同方式共享）。据此，(a) 本文明确署名数据来源；(b) 用途为非商业性使用（数据分析与教学研究）；(c) **派生数据 `data/clean/` 以相同协议共享**，许可副本见 `data/clean/LICENSE`。
5. **可复现**：所有随机过程（如散点抖动）固定随机种子；配色、分箱阈值、窗口参数全部写在脚本中，重跑即得同一张图。

---

## 七、AI 使用披露

本项目的 Python 代码框架、模型参数建议、图表排版逻辑与部分文本润色借助 AI 辅助完成；数据清洗逻辑、全部关键指标（97,308 单、94,136 户、3.03%、0.49%、79.71%、52.72%、28.79% 等）与三条商业建议均由本人逐项核验并在本地复跑确认。AI 未参与数据生成，亦未替代结论判断。

---

## 八、已知限制

| # | 限制 | 说明 |
|---|---|---|
| 1 | 序列仅 20 个月 | 不足两个完整季节周期，Holt-Winters 季节项无法估计，只能退化为趋势外推 |
| 2 | 缺少外生变量 | 无营销活动、流量来源、竞品数据，留存下降无法归因到具体运营动作 |
| 3 | 同期群口径 | 以窗口内首单定义，2016 年首购客户被推后计入，早期群体规模略高估 |
| 4 | 地理精度 | 州级质心由客户经纬度均值计算，未引入外部边界数据（规避来源不明的 geojson） |
