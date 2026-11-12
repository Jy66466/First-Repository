# BA-CH02-17 输入说明

运行入口需要 5 个 CSV（教材"案例 1"目录下的本地授权副本，不随实验发布）：

| 参数 | 文件 | 编码 | 结构（PBIX 实测一致） |
| --- | --- | --- | --- |
| `--orders` | 订单表.csv | gbk | OrderID, EmployeeID, ShipProvince, OrderDate（860 行） |
| `--details` | 订单表明细表.csv | gbk | 订单ID, 产口ID, 销售金额, 销售成本（2,185 行；PBIX 中重命名为 OrderID/ProductID/sales/Cost） |
| `--employees` | 雇员表.csv | utf-8-sig | EmployeeID, FullName, Age, gender, City, store（7 行，Northwind 演示数据） |
| `--products` | 商品表.csv | utf-8-sig | ProductID, ProductName, CategoryID（77 行） |
| `--categories` | 商品类型表.csv | utf-8-sig | CategoryID, CategoryName, Description（8 行） |

运行输出为聚合 JSON 摘要（订单数、明细行数、销售额、成本、利润、年汇总），
不输出任何逐笔明细行。

自动化测试使用人工构造的星型数据（3 订单 / 4 明细 / 2 员工 / 2 商品），
覆盖利润计算、未匹配键保留、聚合口径与总额校验。
