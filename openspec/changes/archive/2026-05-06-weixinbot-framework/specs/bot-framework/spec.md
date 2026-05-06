## ADDED Requirements

### Requirement: WeixinBot Entry Class
系统 SHALL 提供 `WeixinBot` 作为一站式入口，集成所有模块。

#### Scenario: 创建 bot 实例
- **WHEN** 用户调用 `WeixinBot(WeixinBotConfig.from_env())`
- **THEN** 系统 SHALL 初始化 WeixinClient、CommandRouter、HandlerRegistry、ModeManager，并注册内置 /help 指令

#### Scenario: 阻塞式启动
- **WHEN** 用户调用 `bot.run()`
- **THEN** 系统 SHALL 自动检查登录状态（未登录则触发 QR 扫码），启动长轮询消息循环，阻塞直到收到 SIGINT/SIGTERM

#### Scenario: 异步启动
- **WHEN** 用户调用 `await bot.start()`
- **THEN** 系统 SHALL 非阻塞启动，返回后用户可通过 `await bot.wait()` 等待结束

### Requirement: Configuration Management
系统 SHALL 支持通过 .env 文件和环境变量加载配置。

#### Scenario: 从 .env 加载
- **WHEN** 调用 `WeixinBotConfig.from_env()`
- **THEN** 系统 SHALL 加载 .env 文件中的 WEIXIN_* 前缀配置（state_dir、log_level 等）和 Agent 相关配置（HERMES_*、OPENCODE_*）

#### Scenario: 无必填项
- **WHEN** .env 为空或不存在
- **THEN** 系统 SHALL 使用默认值正常启动（微信不需要 AppKey/Secret，凭证通过 QR 扫码获取）

### Requirement: Event Dispatch Pipeline
系统 SHALL 实现统一事件分发管道：用户鉴权 → 指令路由 → 模式转发 → 事件处理器。

#### Scenario: 分发优先级
- **WHEN** 收到用户消息
- **THEN** 系统 SHALL 依次尝试: 1) 用户白名单检查，2) CommandRouter 指令匹配，3) ModeManager 模式转发，4) HandlerRegistry 事件处理器

#### Scenario: 指令拦截
- **WHEN** 消息文本以 `/` 开头且匹配已注册指令
- **THEN** 系统 SHALL 执行指令处理函数并跳过后续处理

#### Scenario: 群聊限制
- **WHEN** is_group 获取 WeChat 消息来源
- **THEN** is_group SHALL 始终返回 False（WeChat 仅支持 P2P）；群聊限制指令 SHALL 回复 "微信暂不支持群聊功能"

### Requirement: Graceful Shutdown
系统 SHALL 支持优雅关闭。

#### Scenario: Ctrl+C 关闭
- **WHEN** 收到 SIGINT 或 SIGTERM
- **THEN** 系统 SHALL 中断长轮询请求，关闭 HTTP 客户端，停止 token 刷新，然后退出

### Requirement: Proactive Messaging
系统 SHALL 支持主动发送消息（不需要用户先发消息触发）。

#### Scenario: 主动推送
- **WHEN** 调用 `bot.send_text(receiver, content)` 且有该用户的 context_token 缓存
- **THEN** 系统 SHALL 使用缓存的 context_token 发送消息

### Requirement: Single Account Scope
系统 SHALL 在单个进程中只支持一个微信账号。

#### Scenario: 账号唯一性
- **WHEN** WeixinBot 初始化并完成 QR 扫码登录
- **THEN** accountId 由 QR 扫码返回的 ilink_bot_id 派生，系统 SHALL 确保该进程内仅维护此一账号的会话

### Requirement: Health Check Command
系统 SHALL 提供 /health 指令返回系统状态。

#### Scenario: 健康检查
- **WHEN** 用户发送 `/health`
- **THEN** 系统 SHALL 返回登录状态、监控状态、上次成功 getUpdates 时间戳、活跃模式会话数
