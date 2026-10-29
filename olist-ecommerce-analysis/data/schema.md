# 数据字典（data/clean）

> 适用对象：`02_clean.py` 产出的 7 张 clean 表
> 数据来源：Kaggle · Brazilian E-Commerce Public Dataset by Olist（CC BY-NC-SA 4.0）
> 生成脚本：`scripts/02_clean.py`　|　生成日期：2026-10-26（首次运行后请补运行时间戳）
> 编码：**UTF-8 with BOM（utf-8-sig）** —— 下游读取请统一 `encoding="utf-8-sig"`，否则首列名会带 BOM 字符
> 空值：CSV 中以空字符串表示；布尔列可能为空（三态：True / False / NA）

## 0. 全局口径

| 项 | 口径 |
|---|---|
| 主分析时间窗 | 2017-01-01 00:00:00 ~ 2018-08-31 23:59:59 |
| 主分析订单状态 | `delivered`（已送达）＋ `shipped`（已发货在途） |
| 客户主键 | `customer_unique_id`（真实客户）；`customer_id` 仅作订单级关联键 |
| GMV 口径 | 订单级 `payment_total`（`payment_value` 按订单汇总，含运费） |
| 品类销售额口径 | 明细级 `price` 汇总（不含运费） |
| 邮编口径 | 5 位字符串（原始为整数，前导 0 已用 `zfill(5)` 还原） |
| 异常值处理 | 只标记不删除，见各表 `is_*_outlier` 列 |
| 未匹配处理 | 一律保留记录，分类字段填 `unknown`，不静默丢行 |

---

## 1. `orders_clean.csv` —— 订单主表（一行一订单）

主分析集，已按时间窗与状态过滤。主键 `order_id`。

| 字段 | 类型 | 含义 | 键 |
|---|---|---|---|
| order_id | string | 订单唯一标识 | **PK** |
| customer_id | string | 订单级客户键（每单唯一） | FK → 原始 customers |
| customer_unique_id | string | 真实客户唯一标识（同一人多次下单共用） | FK → `customers_clean` |
| order_status | string | 订单状态（主分析集仅 delivered / shipped） | |
| order_purchase_timestamp | datetime64[ns] | 下单时间 | |
| order_approved_at | datetime64[ns] | 支付审批时间，可为空（未审批/已取消） | |
| order_delivered_carrier_date | datetime64[ns] | 交承运商时间，可为空（未发货） | |
| order_delivered_customer_date | datetime64[ns] | 送达客户时间，可为空（未送达） | |
| order_estimated_delivery_date | datetime64[ns] | 承诺送达日期 | |
| payment_total | float64 | 订单总支付金额（含运费），无支付记录记 0 | |
| payment_record_cnt | int64 | 支付记录条数（一单多支付） | |
| payment_type_cnt | int64 | 支付方式种类数 | |
| payment_type_main | string | 主支付方式（出现次数最多；并列按字典序取首个） | |
| payment_installments_mean | float64 | 分期数均值 | |
| item_cnt | int64 | 商品行数（一单多商品） | |
| item_value_total | float64 | 商品金额合计（不含运费） | |
| freight_total | float64 | 运费合计 | |
| seller_cnt | int64 | 涉及卖家数 | |
| customer_state | string | 收货州（2 字母），缺失记 unknown | FK → 地理 |
| customer_city | string | 收货城市，缺失记 unknown | |
| customer_zip_code_prefix | string | 收货邮编前 5 位 | FK → `geo_prefix` |
| review_score | float64 | 评价分（1–5），无评价为空 | |
| review_id | string | 评价 ID，无评价为空 | |
| purchase_year | Int64 | 下单年 | |
| purchase_quarter | Int64 | 下单季度（1–4） | |
| purchase_month | Int64 | 下单月（1–12） | |
| purchase_ym | string | 下单年月（`YYYY-MM`） | |
| purchase_weekday | Int64 | 下单星期（0=周一 … 6=周日） | |
| purchase_weekday_name | string | 下单星期中文名（周一…周日） | |
| delivery_days | Int64 | 下单→送达天数，未送达为空 | |
| is_late | boolean | 是否晚于承诺日期送达；未送达/无承诺日期为 NA | |
| is_payment_outlier | boolean | 订单支付金额 > P99 阈值 | |
| is_high_freight | boolean | 订单运费合计 > P99 阈值 | |
| has_payment | boolean | 是否存在支付记录 | |
| has_item | boolean | 是否存在商品明细 | |
| has_review | boolean | 是否存在评价 | |

**已知特征**：原始 99,441 订单中，支付表仅覆盖 99,440 个订单、明细表覆盖 98,666 个 → 存在少量 `has_payment=False` / `has_item=False` 的记录，均予保留并用布尔列标记，不做删除。

---

## 2. `orders_all_status.csv` —— 全状态订单表（供漏斗分析）

字段与 `orders_clean` **完全一致**，区别仅在于：**不做时间窗与状态过滤**，保留 2016-09 ~ 2018-10 全部 8 种状态。

用途：订单履约漏斗（created → approved → invoiced → processing → shipped → delivered）、取消率分析。
注意：该表**不可**用于 GMV、RFM、同期群等核心分析，否则会因不完整月份与无效订单导致口径失真。

---

## 3. `items_clean.csv` —— 订单明细表（一行一订单项）

保留订单项粒度（不压缩到订单级），供品类分析使用。主键 (`order_id`, `order_item_id`)。

| 字段 | 类型 | 含义 | 键 |
|---|---|---|---|
| order_id | string | 订单标识 | **PK(1)**，FK → `orders_clean` |
| order_item_id | int64 | 单内商品序号 | **PK(2)** |
| product_id | string | 商品标识 | FK → 原始 products |
| seller_id | string | 卖家标识 | FK → 原始 sellers |
| shipping_limit_date | datetime64[ns] | 卖家发货截止时间 | |
| price | float64 | 商品单价（不含运费） | |
| freight_value | float64 | 该行运费 | |
| product_category_name | string | 品类葡语原名（缺失记 unknown） | |
| product_category_en | string | 品类英文名（经翻译表；未覆盖记 unknown） | |
| order_purchase_timestamp | datetime64[ns] | 下单时间（由订单表左连补入） | |
| purchase_year | Int64 | 下单年 | |
| purchase_quarter | Int64 | 下单季度 | |
| purchase_month | Int64 | 下单月 | |
| purchase_ym | string | 下单年月 | |
| purchase_weekday | Int64 | 下单星期（0=周一） | |
| purchase_weekday_name | string | 下单星期中文名 | |
| is_price_outlier | boolean | 单价超出 IQR 上界（Q3 + 1.5×IQR） | |
| is_freight_outlier | boolean | 运费 > P99 阈值 | |

**用途**：波士顿矩阵（品类份额×增速）、帕累托/ABC（品类累计贡献）、品类结构图。
**注意**：该表一单多行，算"订单数/客单价"必须先聚合到订单级，不可直接对行计数。

---

## 4. `customers_clean.csv` —— 客户维表（一行一客户）

主键 `customer_unique_id`。

| 字段 | 类型 | 含义 | 键 |
|---|---|---|---|
| customer_unique_id | string | 真实客户唯一标识 | **PK** |
| first_order_ts | datetime64[ns] | 首单下单时间（同期群 cohort 依据） | |
| last_order_ts | datetime64[ns] | 最近一次下单时间 | |
| order_cnt | int64 | 累计订单数 | |
| customer_zip_code_prefix | string | 首单收货邮编前 5 位 | FK → `geo_prefix` |
| customer_city | string | 首单收货城市 | |
| customer_state | string | 首单收货州 | |
| lat | float64 | 首单收货地纬度（邮编前缀中位数；缺失用同州中位数补） | |
| lng | float64 | 首单收货地经度（同上） | |
| is_geo_imputed | boolean | 坐标是否为填补值（True = 未直接匹配到 geo_prefix） | |

**地理口径**：州/市/邮编/坐标全部取**首单收货地址**，保证一客户一行、维度不膨胀。
**注意**：`order_cnt` 仅作维度属性展示；RFM 的 R/F/M 由 `03_rfm.py` 独立计算，避免两处口径打架。

---

## 5. `payments_order.csv` —— 订单级支付汇总

由 103,886 行支付记录聚合而成。主键 `order_id`。

| 字段 | 类型 | 含义 | 键 |
|---|---|---|---|
| order_id | string | 订单标识 | **PK**，FK → `orders_clean` |
| payment_total | float64 | 该订单支付总额（多行相加） | |
| payment_record_cnt | int64 | 支付记录条数 | |
| payment_type_cnt | int64 | 支付方式种类数 | |
| payment_installments_mean | float64 | 分期数均值 | |
| payment_type_main | string | 主支付方式 | |
| is_payment_outlier | boolean | 支付总额 > P99 阈值 | |

**为什么必须预聚合**：原始表一单最多 29 条支付记录，直接与明细表 join 会使金额成倍放大。

---

## 6. `reviews_order.csv` —— 订单级评价（已去重）

主键 `order_id`。

| 字段 | 类型 | 含义 | 键 |
|---|---|---|---|
| order_id | string | 订单标识 | **PK**，FK → `orders_clean` |
| review_id | string | 评价 ID | |
| review_score | int64 | 评分 1–5 | |
| review_comment_title | string | 评价标题（缺失率高，约 88%） | |
| review_comment_message | string | 评价正文（缺失率约 59%，葡萄牙语） | |
| review_creation_date | datetime64[ns] | 评价创建日期 | |
| review_answer_timestamp | datetime64[ns] | 评价回复时间 | |

**去重规则**：① 先按 `review_id` 去重（保留最后一条）；② 同一订单多条评价时，按 `review_creation_date`、`review_answer_timestamp` 取**最新一条**。
**注意**：评论文本为葡萄牙语，中文情感库（snownlp）不适用；本次不做文本模型。

---

## 7. `geo_prefix.csv` —— 邮编前缀坐标表

由 1,000,163 行地理记录聚合而成（平均每前缀 52.6 条）。主键 `zip_code_prefix`。

| 字段 | 类型 | 含义 | 键 |
|---|---|---|---|
| zip_code_prefix | string | 邮编前 5 位（5 位字符串） | **PK** |
| lat | float64 | 该前缀下所有记录的纬度**中位数** | |
| lng | float64 | 该前缀下所有记录的经度**中位数** | |
| geo_record_cnt | int64 | 该前缀对应的原始记录条数 | |

**为什么取中位数**：同一邮编存在大量重复坐标（最多 1146 条），中位数抗离群点，比均值稳定；且聚合后主键唯一，可直接 join 不膨胀。

---

## 8. `outputs/tables/clean_summary.csv` —— 清洗汇总

| 字段 | 类型 | 含义 |
|---|---|---|
| table | string | 表名（含清洗阶段，如 orders_clean(全量) / orders_clean(主分析集)） |
| rows_raw | Int64 | 清洗前行数 |
| rows_clean | Int64 | 清洗后行数 |
| rows_dropped | Int64 | 减少行数（聚合类表为负对应的压缩量，见 note） |
| avg_missing_pct_before | float64 | 清洗前平均缺失率（%） |
| avg_missing_pct_after | float64 | 清洗后平均缺失率（%） |
| note | string | 处理说明 |

> 聚合类表（payments/geo）行数减少属**预期压缩**，不是数据丢失；原始文件保持不动。

---

## 9. 表间关系

```
geo_prefix (zip_code_prefix) 1 ──── n customers_clean
                                      │
customers_clean (customer_unique_id) 1 ──── n orders_clean
                                                 │
                            ┌────────────────────┼────────────────────┐
                       1 ───┴── n          1 ──────┴────── n      1 ───┴── n
                    items_clean        payments_order          reviews_order
                    (order_id,          (order_id)              (order_id)
                     order_item_id)
```

- 全部为 `order_id` / `customer_unique_id` 上的 **1 : n** 关系，已消除多对多。
- 关联方向一律 `orders_clean LEFT JOIN 其他表`，保证主表行数不变。

---

## 10. 未处理项与已知局限（写论文时如实交代）

| 项 | 现状 | 原因 |
|---|---|---|
| 履约类日期缺失（送达 2.98%、交承运商 1.79%、审批 0.16%） | 保留空值，只统计不填充 | 缺失本身即业务信息（未送达/未审批），填充会捏造履约事实 |
| 商品品类缺失 1.85% | 记 `unknown`，保留记录 | 剔除会改变总量口径，导致品类 GMV 合计对不上总额 |
| 评论文本缺失 58.70% | 保留空值 | 多数用户只打分不写评；本次不做文本模型 |
| 异常值 | 只标记不删除 | 极端大额订单是真实的批发/大件交易，删除会低估 GMV |
| 2016 年与 2018-09 后订单 | 排除出主分析集 | 前者过稀疏、后者月份不完整，会扭曲同比与趋势 |
| 坐标填补 | 同州中位数填补并标记 | 少量邮编未匹配到 geo_prefix；标记后可随时剔除复算 |
| 联邦区/州名 | 保留 2 字母缩写（如 SP、RJ） | 原始数据即如此，未另建州名映射表 |

---

## 11. 数据质量发现（建议写进论文"数据清洗"一节，属加分细节）

| 发现 | 证据 | 影响与处理 |
|---|---|---|
| **翻译表文件带 UTF-8 BOM** | `product_category_name_translation.csv` 首列表头实为 `\ufeffproduct_category_name` | 若按 `encoding="utf-8"` 读取，与商品表按品类关联时**全部匹配失败**，`product_category_en` 会整列退化为 `unknown` 且不报错（静默错误）。已在 `read_raw()` 中统一改用 `utf-8-sig` 并二次清理列名 |
| 支付表少 1 个订单 | 支付表覆盖 99,440 个订单，订单表 99,441 个 | 保留该订单，`has_payment=False`、`payment_total=0`，不删除（左连接原则） |
| 明细表少 775 个订单 | 明细覆盖 98,666 个订单 | 同上，`has_item=False` 标记 |
| 评价 ID 存在重复 | 99,224 行但 `review_id` 唯一值仅 98,410 | 先按 `review_id` 去重，再按订单取最新一条 |
| 547 个订单有多条评价 | profiling 结构核验 | 按评价创建时间取最新，避免评分均值被重复加权 |
| 邮编前缀以整数存储 | 如 `1037` 实为 `01037` | `zfill(5)` 还原为 5 位字符串，否则与地理表无法对齐 |
