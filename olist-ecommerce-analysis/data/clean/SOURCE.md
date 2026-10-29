# data/clean 数据来源与许可说明

本目录下的 7 张 CSV 均由 `scripts/02_clean.py` 从原始数据清洗派生，不含任何生成或补足记录。

- **原始数据集**：Brazilian E-Commerce Public Dataset by Olist
- **数据源 URL**：https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
- **获取方式**：Kaggle 官方命令行工具（`kaggle datasets download -d olistbr/brazilian-ecommerce`），未使用爬虫、未模拟登录、未做网页解析
- **获取日期**：2026-10-26
- **许可协议**：CC BY-NC-SA 4.0（署名—非商业性使用—相同方式共享 4.0 国际）
- **派生数据**：`data/clean/` 下 7 张 CSV —— 订单主表、订单项明细、客户维度、订单级支付、订单级评价、邮编地理、全状态订单
- **生成脚本**：`scripts/02_clean.py`
- **真实性**：未使用 Faker 或任何合成数据工具；未修改 `data/raw/` 中的原始文件
- **许可副本**：`data/clean/LICENSE`

## 共享义务说明

CC BY-NC-SA 4.0 的 SA 条款要求：以本数据为基础的演绎作品须以相同协议共享。
因此本目录（派生数据）随附 `LICENSE` 副本，任何再分发须保留署名并沿用同一协议。
本项目仅用于数据分析与教学研究，属非商业性使用。
