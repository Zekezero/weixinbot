## ADDED Requirements

### Requirement: Command Registration
系统 SHALL 支持通过装饰器注册 /xxx 指令，提供标准的指令路由接口。

#### Scenario: 注册指令
- **WHEN** 使用 `@bot.command("ping", description="测试连通性")`
- **THEN** 系统 SHALL 将该函数注册为 /ping 指令的处理器

#### Scenario: 指令别名
- **WHEN** 使用 `aliases=["p"]` 参数
- **THEN** 系统 SHALL 同时注册 /p 作为别名

### Requirement: Command Routing
系统 SHALL 匹配并执行已注册指令。

#### Scenario: 指令匹配
- **WHEN** 收到 `/ping` 文本消息
- **THEN** 系统 SHALL 调用对应处理函数，传入 (msg, bot) 参数

#### Scenario: 未匹配
- **WHEN** 消息不以 `/` 开头或不匹配任何已注册指令
- **THEN** CommandRouter.try_handle() SHALL 返回 False，消息继续传递到下游处理器

### Requirement: Built-in Help Command
系统 SHALL 自动注册 /help 指令。

#### Scenario: 显示帮助
- **WHEN** 用户发送 `/help`
- **THEN** 系统 SHALL 列出所有已注册指令及其描述

### Requirement: Scene Restriction
系统 SHALL 支持 p2p_only 和 group_only 场景限制。

#### Scenario: P2P 限制
- **WHEN** 指令标记 `p2p_only=True` 但在群聊中触发
- **THEN** 系统 SHALL 回复提示信息并不执行指令

#### Scenario: 群聊限制场景
- **WHEN** group_only 指令在 WeChat 上触发（WeChat 始终为 P2P）
- **THEN** 系统 SHALL 回复 "此指令仅支持群聊，微信当前不支持群聊功能"
