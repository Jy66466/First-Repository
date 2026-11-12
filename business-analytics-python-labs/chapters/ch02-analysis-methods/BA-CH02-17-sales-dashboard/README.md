# BA-CH02-17 销售看板：分省销售分析

实验用 Python（pandas）等价实现教材分省销售分析.pbix 经 Power BI Desktop
实测验证的核心业务逻辑：

1. **星型模型装配**：订单明细 → 订单 → 雇员；订单明细 → 商品 → 商品类型
   （与 PBIX 实测提取的 5 条多对一、单向、活动关系一致）；
2. **显式计算列等价**：`orderyear = YEAR(OrderDate)`、
   `ordermonth = MONTH(OrderDate)`、`利润 = sales - Cost`
   （均从 PBIX 模型逐字提取后转写，非猜测）；
3. **隐式聚合**：按省份、年份、商品类别、员工的销售额/利润汇总
   （PBIX 中无任何显式度量值，全部为隐式 Sum）；
4. **总额校验**：利润恒等于销售额减成本。

```powershell
python run_sales_dashboard.py --orders <orders.csv> --details <details.csv> --employees <employees.csv> --products <products.csv> --categories <categories.csv>
python -m pytest -q
```

## Power BI 实测证据（P1.3-02）

- 模型经 Power BI Desktop（2.159.1231.0）打开并用 TOM/ADOMD 只读提取；
- 参考核对：订单 860、明细 2,185、销售额 5,716,509、成本 4,060,400、
  利润 1,656,109；省份 19、年份 2（2020/2021）、类别 8、员工 7、商品 77；
- Python 独立重算与 PBIX EVALUATE 结果逐项一致（见阶段报告）。

## 数据边界

- 教材 CSV（案例 1）为 Northwind 中文演示数据，仅本地只读用于参考核对，
  **不随实验发布**；
- 公开目录只含人工构造的合成数据测试（虚构省份/员工/商品）；
- 员工/商品记录一律不进入公开仓库。

## 验证边界

- “快速搭建销售看板.pbix”（17a）的数据源之一不在教材目录且两表无关系，
  仅作教学演示，本实验不迁移；
- 报表视觉对象的交互行为（交叉突出显示、工具提示）属于 Power BI 运行时
  行为，Python 以参数化聚合替代，不宣称复现交互体验。
