## ADDED Requirements

### Requirement: BaseRenderer Abstract Interface
系统 SHALL 定义可插拔的 BaseRenderer 抽象接口，通过 EventBus 事件驱动渲染。

#### Scenario: 接口定义
- **WHEN** 实现新的渲染器（如未来的 CardRenderer）
- **THEN** 开发者只需继承 BaseRenderer 并实现 on_response_start / on_response_chunk / on_response_end / on_response_error 四个方法

#### Scenario: 注册渲染器
- **WHEN** WeixinBot 初始化时
- **THEN** 系统 SHALL 自动实例化配置指定的 Renderer 类，Renderer 构造时 SHALL 订阅 EventBus 的 ResponseStart/Chunk/End/Error 事件

#### Scenario: 生命周期关闭
- **WHEN** WeixinBot.stop() 被调用
- **THEN** 系统 SHALL 调用 renderer.close()，该方法 SHALL 取消订阅所有 EventBus 处理器

### Requirement: TextRenderer Default Implementation
系统 SHALL 提供 TextRenderer 作为默认渲染器，将流式 Agent 响应转为分段文本消息发送。

#### Scenario: 累积发送
- **WHEN** 收到连续 ResponseChunk 事件
- **THEN** TextRenderer SHALL 累积文本到 buffer，按时间间隔（默认 3s）或字符阈值（默认 2000 字）触发中间发送

#### Scenario: 最终发送
- **WHEN** 收到 ResponseEnd 事件
- **THEN** TextRenderer SHALL flush 剩余 buffer，超过 3000 字时按段落边界切分为多条消息

#### Scenario: 错误渲染
- **WHEN** 收到 ResponseError 事件
- **THEN** TextRenderer SHALL 发送错误提示文本

#### Scenario: 文本兜底
- **WHEN** 中间发送失败（网络错误等）
- **THEN** TextRenderer SHALL 在 ResponseEnd 时尝试发送完整文本作为兜底

### Requirement: Multi-Channel Support
BaseRenderer 接口 SHALL 支持多通道输出概念。

#### Scenario: 通道路由
- **WHEN** ResponseChunk 携带 channel 字段（如 "main"、"tool"）
- **THEN** Renderer SHALL 按通道独立管理输出状态

#### Scenario: 事件范围说明
- **WHEN** Renderer 处理 ResponseStart/End/Error 事件
- **THEN** ResponseStart/End/Error 事件为非通道限定事件；仅 ResponseChunk 携带 channel 标记。Renderer SHALL 按 (user_id, session_id, channel) 元组维护每通道状态

#### Scenario: TextRenderer 通道处理
- **WHEN** TextRenderer 收到非 "main" 通道的 chunk
- **THEN** TextRenderer SHALL 将所有通道合并到单一文本输出（当前微信限制下的降级策略）

### Requirement: Throttling
Renderer SHALL 实现节流机制，避免消息轰炸。

#### Scenario: 时间节流
- **WHEN** 连续 ResponseChunk 间隔小于配置的推送间隔
- **THEN** Renderer SHALL 缓冲内容直到间隔达到阈值

#### Scenario: 字符节流
- **WHEN** 累积文本量未达到最小推送字符数
- **THEN** Renderer SHALL 继续缓冲（除非是 finalize 事件）

### Requirement: Future Card Renderer Compatibility
BaseRenderer 设计 SHALL 保证未来 CardRenderer 可无缝替换 TextRenderer。

#### Scenario: 配置切换
- **WHEN** 修改配置 `renderer_type = "card"`（未来）
- **THEN** 系统 SHALL 实例化 CardRenderer 替代 TextRenderer，无需修改框架代码

#### Scenario: 事件兼容
- **WHEN** 实现 CardRenderer
- **THEN** CardRenderer SHALL 可以复用标准 Renderer 的多通道管理、续接逻辑和 finalize 模式

### Requirement: Method Naming Convention
BaseRenderer 公共接口和内部 EventBus 包装器 SHALL 遵循命名约定。

#### Scenario: 接口命名
- **WHEN** 实现 Renderer 子类
- **THEN** 公共接口 SHALL 使用 on_response_start / on_response_chunk / on_response_end / on_response_error；内部 EventBus 包装器 SHALL 使用 _handle_start / _handle_chunk / _handle_end / _handle_error
