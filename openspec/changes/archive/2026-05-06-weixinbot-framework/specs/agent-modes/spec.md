## ADDED Requirements

### Requirement: Mode Manager
系统 SHALL 支持用户级有状态 Agent 模式管理，提供标准的模式管理框架。

#### Scenario: 进入模式
- **WHEN** 用户发送 `/opencode` 或 `/hermes`
- **THEN** 系统 SHALL 调用对应 AgentAdapter.create_session()，将用户设为该模式，后续消息自动转发到 Agent

#### Scenario: 退出模式
- **WHEN** 用户发送 `/exit`
- **THEN** 系统 SHALL 退出当前模式，后续消息回到正常指令/事件处理流程

#### Scenario: 新建会话
- **WHEN** 用户发送 `/new`
- **THEN** 系统 SHALL 在当前模式下创建新 Agent 会话

#### Scenario: 模式转发
- **WHEN** 用户在模式中发送非指令消息
- **THEN** 系统 SHALL 将消息转发到对应 AgentAdapter.send()，并加锁防止并发

### Requirement: Agent Adapter Interface
系统 SHALL 定义平台无关的 AgentAdapter 抽象接口。

#### Scenario: 实现新适配器
- **WHEN** 需要接入新 Agent（如 Claude Code）
- **THEN** 开发者只需实现 create_session() / send() / destroy_session() 三个方法

### Requirement: Event Bus Decoupling
系统 SHALL 通过 EventBus 解耦 Adapter 和 Renderer。

#### Scenario: 事件流
- **WHEN** AgentAdapter 处理 Agent 响应
- **THEN** Adapter SHALL 通过 EventBus emit ResponseStart → ResponseChunk(s) → ResponseEnd/Error 事件

#### Scenario: 异常隔离
- **WHEN** 某个事件处理器抛出异常
- **THEN** EventBus SHALL 记录错误日志但不阻断其他处理器
