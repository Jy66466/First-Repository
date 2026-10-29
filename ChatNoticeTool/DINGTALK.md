# 钉钉本地群聊文本消息导出 + 待办桥接（本目录新增能力）

> 本文件只描述**新增**的钉钉适配层。项目原有的 QQ / 微信能力与全部源码**未做任何改动**
> （已对 41 个原始文件做 SHA-256 校验，全部一致）。

## 定位与边界（与项目一致，实现中逐项强制）

| 约束 | 实现方式 |
|---|---|
| 完全离线 | 运行前硬阻断 socket 创建；任何出站网络尝试直接抛错 |
| 只读 | 钉钉数据目录（`F:\JY\dingding\...`）只以读模式打开；所有解密产物写入项目 `runtime/` 临时目录并在退出时删除 |
| 按需执行 | 每条命令一次性执行；无守护进程、无托盘、无定时器、无开机自启、无后台线程 |
| 不依赖云端 | 全程无网络请求；仅读取本机已缓存的本地消息 |
| 导出仅限群聊 | 导出前强制校验 `tbconversation.type=2`；单聊、未知群 ID 一律硬拒绝 |
| 仅文本内容 | 只取 `contentType=1` 且 `recallStatus=0` 的消息；媒体/卡片/文件不下载、不解析 |
| 逐条建待办 | 桥接脚本为每条消息生成一条待办，稳定 ID `dingtalk:<群cid>:<消息mid>`，重复导入是更新而非新建 |
| QQ/微信能力完整保留 | 未修改任何现有文件；钉钉是独立入口（`dingtalk_probe.py` / `dingtalk_export.py`） |

## 三个新文件

| 文件 | 作用 |
|---|---|
| `dingtalk_probe.py` | 阶段0只读探针：验证 V3 解密、库完整性、表结构；不读正文 |
| `dingtalk_export.py` | 群聊列表 + 指定群/时间窗的文本导出（`exports/<批次>/`） |
| `todo_import.py` | 桥接：把已导出的群聊文本逐条写入桌面待办库 `state/todos.sqlite3` |

## 使用方法

统一用 Anaconda 解释器（本机唯一带 Tkinter 且已装 cryptography 的 Python）：

```powershell
# 0. 阶段0探针（只读，验证环境；可重复运行）
F:\JY\Anaconda\Anaconda3\python.exe -B -X utf8 dingtalk_probe.py

# 1. 列出本地群聊（不列单聊、不读正文）
F:\JY\Anaconda\Anaconda3\python.exe -B -X utf8 dingtalk_export.py groups

# 2. 导出指定群 + 时间窗的文本消息（必须 --confirm）
F:\JY\Anaconda\Anaconda3\python.exe -B -X utf8 dingtalk_export.py export `
  --group-id <群cid> --since 2026-09-01 --until 2026-10-15 --confirm

# 3. 把导出结果逐条写入桌面待办（先 --dry-run 预览）
F:\JY\Anaconda\Anaconda3\python.exe -B -X utf8 todo_import.py --latest --dry-run
F:\JY\Anaconda\Anaconda3\python.exe -B -X utf8 todo_import.py --latest

# 4. 打开桌面待办组件查看
F:\JY\Anaconda\Anaconda3\python.exe -B -X utf8 todo_widget.py
```

## 幂等与状态保持

- 同一批消息重复导入：标题/正文更新，**已完成、已移除状态不被覆盖**。
- 待办组件本身**永不读取**钉钉/QQ/微信数据，只轮询自己的 `state/todos.sqlite3`；
  桥接是聊天数据进入待办的唯一通道，且必须由用户显式执行。

## 已验证事项（2026-10-15）

- 探针：V3 解密通过、`PRAGMA quick_check=ok`、214 张表、`tbmsg_000–127` 共 128 分片、
  本机 25 个活跃群聊；`state/dingtalk-probe.json` 存档。
- 导出：41 条群文本消息正确解码（发送者昵称、毫秒时间戳、@ 提及保留）。
- 守卫：无 `--confirm` 拒绝 / 未知群 ID 拒绝 / 单聊会话硬拒绝，均验证通过。
- 桥接：dry-run、实导入、重复导入幂等、done 状态保持，均验证通过。
- 只读证据：`dingtalk.db` 修改时间保持 2026-10-14 09:47 不变；`runtime/` 退出后为空。
- 原始文件：41/41 SHA-256 与上游发布一致。

## 限制

- 只支持本机 **V3** 格式的钉钉数据目录（当前账号即 V3）。
- 只能读到**已缓存到本机**的消息；未缓存的历史不会凭空出现。
- 仅导出文本；图片、语音、文件、卡片、审批等类型不解析（计数可见，正文不导出）。
- 客户端升级后若表结构变化，探针会失败——这是**设计上的安全行为**，请先跑探针确认。
