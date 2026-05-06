## ADDED Requirements

### Requirement: QR Code Login Flow
系统 SHALL 支持微信 QR 码扫描登录。启动时检查本地是否有已保存的凭证；若无或已过期，SHALL 自动触发 QR 登录流程，在终端显示二维码供用户扫描。

#### Scenario: 首次登录
- **WHEN** 用户首次启动 bot 且无本地凭证
- **THEN** 系统调用 `GET /ilink/bot/get_bot_qrcode?bot_type=3` 获取二维码，在终端渲染 QR 码并显示扫码 URL，然后长轮询 `GET /ilink/bot/get_qrcode_status` 等待扫码确认

#### Scenario: QR 码过期自动刷新
- **WHEN** 轮询状态返回 `expired`
- **THEN** 系统 SHALL 自动重新获取 QR 码（最多 3 次），刷新终端显示

#### Scenario: IDC 重定向
- **WHEN** 轮询状态返回 `scaned_but_redirect` 并携带 `redirect_host`
- **THEN** 系统 SHALL 切换 API 基础 URL 为 `https://{redirect_host}` 并继续轮询

#### Scenario: 登录成功
- **WHEN** 轮询状态返回 `confirmed` 并携带 `bot_token` 和 `ilink_bot_id`
- **THEN** 系统 SHALL 保存凭证到 `~/.weixinbot/accounts/{accountId}.json`（权限 0o600），并返回登录结果

### Requirement: Token Persistence
系统 SHALL 持久化登录凭证，支持重启后免扫码恢复。

#### Scenario: 重启恢复
- **WHEN** 用户重启 bot 且本地存在有效凭证
- **THEN** 系统 SHALL 直接加载凭证启动长轮询，无需重新扫码

#### Scenario: 登出
- **WHEN** 用户调用 `logout()` 函数
- **THEN** 系统 SHALL 清除所有本地保存的凭证文件

### Requirement: Long-Poll Message Loop
系统 SHALL 通过长轮询 `POST /ilink/bot/getupdates` 持续接收消息，支持断点续传。

#### Scenario: 正常消息接收
- **WHEN** 服务端有新消息
- **THEN** 系统 SHALL 解析 `msgs` 数组中的每条 `WeixinMessage`，提取文本/媒体内容，分发到事件处理管道

#### Scenario: 长轮询超时
- **WHEN** 35 秒内无新消息（客户端超时）
- **THEN** 系统 SHALL 立即发起下一次 getUpdates 请求（正常行为）

#### Scenario: 断点续传
- **WHEN** bot 重启
- **THEN** 系统 SHALL 从本地持久化的 `get_updates_buf` 恢复，从上次位置继续接收消息

#### Scenario: 连续失败退避
- **WHEN** getUpdates 连续失败 3 次
- **THEN** 系统 SHALL 等待 30 秒后重试（之前每次等待 2 秒）

### Requirement: Session Expiry Handling
系统 SHALL 处理会话过期（errcode=-14），进入 1 小时冷却期后提示重新登录。

#### Scenario: 会话过期
- **WHEN** getUpdates 返回 `errcode=-14`
- **THEN** 系统 SHALL 暂停所有 API 调用 1 小时，并在日志中提示用户需要重新登录

### Requirement: Context Token Management
系统 SHALL 为每个用户维护 context_token，用于消息关联。

#### Scenario: Token 缓存
- **WHEN** 收到入站消息携带 `context_token`
- **THEN** 系统 SHALL 缓存该 token（内存 Map，key 为 `accountId:userId`）

#### Scenario: Token 使用
- **WHEN** 发送回复消息
- **THEN** 系统 SHALL 在 `SendMessageReq.msg.context_token` 字段回传对应用户的缓存 token

### Requirement: Message Sending
系统 SHALL 支持通过 `POST /ilink/bot/sendmessage` 发送文本和媒体消息。

#### Scenario: 发送文本
- **WHEN** 调用 `send_text(receiver, content)`
- **THEN** 系统 SHALL 构建 TextItem（type=1），设置 message_type=2（BOT）、message_state=2（FINISH），携带 context_token 发送

#### Scenario: Markdown 转换
- **WHEN** 文本包含 Markdown 格式
- **THEN** 系统 SHALL 自动转换为纯文本（去代码围栏、链接语法、行内格式等）

### Requirement: Typing Indicator
系统 SHALL 在处理消息期间发送 Typing 指示器。

#### Scenario: 开始处理
- **WHEN** 收到用户消息并开始处理
- **THEN** 系统 SHALL 调用 sendTyping(status=1)，每 10 秒刷新一次

#### Scenario: 处理完成
- **WHEN** Agent 响应完毕并发送回复
- **THEN** 系统 SHALL 调用 sendTyping(status=2) 取消指示器

### Requirement: Message Deduplication
系统 SHALL 通过 LRU 缓存去重收到的消息，避免重复处理。

#### Scenario: 消息去重
- **WHEN** getUpdates 返回一条 msg_id 已存在于 LRU 缓存中的消息（容量 10000，TTL 30 分钟）
- **THEN** 系统 SHALL 静默跳过该消息（仅打印 debug 日志）
