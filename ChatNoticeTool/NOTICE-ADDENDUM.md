# 派生新增部分的技术参考与第三方组件

> 本文件为派生仓库对上游 [NOTICE.md](NOTICE.md) 的**追加说明**，不修改、不替代上游声明。
> 派生新增实现（`dingtalk_probe.py` / `dingtalk_export.py` / `todo_import.py` /
> `todo_tasks.py` / `create_shortcut.py`）按 Apache License 2.0 提供。

## 技术参考（钉钉本地数据库格式）

新增的钉钉适配层查阅了公开的钉钉 PC 版本地数据库格式资料，仅用于确认
**格式常量与字段含义**，未复制、未分发、未调用任何第三方导出器的源码或自动化包。

- 钉钉 V3 本地库密钥派生参数（PBKDF2-HMAC-SHA1 → MD5 → AES-128-ECB）为
  **格式常量**（如迭代次数、盐值），属于不受版权保护的客观格式数据。
- 表结构与字段名（`tbconversation`、`tbmsg_000–127`、`contentType`、`recallStatus` 等）
  通过只读 SQLite schema 探针在本机实际库上验证，非摘自他人源码。
- 未引入任何第三方钉钉解密库；依赖仅为上游 `requirements.txt` 已有的 `cryptography`。

## 运行依赖

派生新增部分**不新增**任何第三方运行依赖（沿用上游 `requirements.txt`）。
