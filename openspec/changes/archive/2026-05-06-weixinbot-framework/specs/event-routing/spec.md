## ADDED Requirements

### Requirement: Handler Registration
系统 SHALL 支持通过装饰器注册多类型事件处理器。

#### Scenario: 消息处理器
- **WHEN** 使用 `@bot.on_message()`
- **THEN** 系统 SHALL 将函数注册为 P2P 和群聊消息的处理器

#### Scenario: 消息类型过滤
- **WHEN** 使用 `@bot.on_message(msg_types=[MsgType.TEXT])`
- **THEN** 系统 SHALL 仅对文本消息触发该处理器

### Requirement: Event Dispatch
系统 SHALL 按事件类型分发到匹配的处理器。

#### Scenario: 多处理器
- **WHEN** 同一事件类型注册了多个处理器
- **THEN** 系统 SHALL 按注册顺序依次调用，单个处理器异常不阻断其他处理器

#### Scenario: 无匹配
- **WHEN** 事件类型无注册处理器
- **THEN** 系统 SHALL 静默忽略（仅 debug 日志）
