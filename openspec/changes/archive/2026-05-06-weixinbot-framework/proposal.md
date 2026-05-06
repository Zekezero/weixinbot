## Why

我们需要一个通用的 Python 微信机器人框架。已有一个经过生产验证的内部 IM 机器人框架，验证了 CommandRouter / HandlerRegistry / ModeManager / AgentAdapter / EventBus / Renderer 的架构设计可行性。微信 ilink 协议（ilinkai.weixin.qq.com）已有多个开源 Python 参考实现（nanobot, QwenPaw 等），证明 Python 通信层可行。现在是将成熟的框架架构与微信通信层结合、构建通用微信机器人框架的最佳时机。

## What Changes

- **新建 weixinbot Python 项目**：完整的 Python 异步微信机器人框架
- **复用已验证框架层**：CommandRouter、HandlerRegistry、AgentAdapter、EventBus、ModeManager 直接复用或微调
- **全新微信通信层**：参考现有 Python ilink 实现（主参考 nanobot），包含 QR 登录、长轮询、CDN 加解密、媒体处理
- **通用 Renderer 抽象**：可插拔渲染器设计，默认 TextRenderer（分段文本），架构上保留未来卡片/富文本渲染器的快速接入能力
- **Agent 适配器迁移**：复用 HermesAdapter 和 OpenCodeAdapter（保留流式输出踩坑经验）
- **docs/ 文档体系**：架构文档、ilink 协议文档、开发指南
- **示例代码**：echo bot、OpenAI agent 集成示例

## Capabilities

### New Capabilities

- `weixin-comms`: 微信 ilink 协议通信层 — QR 登录、长轮询 getUpdates、消息收发、Token 管理、会话恢复、消息去重
- `weixin-cdn`: 微信 CDN 媒体处理 — AES-128-ECB 加解密、CDN 上传/下载、SILK 语音转码、MIME 检测
- `bot-framework`: 机器人框架核心 — WeixinBot 入口类、配置管理、生命周期、事件分发管道、单进程单账号
- `command-system`: 指令系统 — /help 自动生成、场景限制
- `event-routing`: 事件路由 — HandlerRegistry、多事件类型注册、消息过滤器
- `agent-modes`: Agent 模式系统 — ModeManager + AgentAdapter + EventBus、用户级有状态会话管理
- `pluggable-renderer`: 可插拔渲染器 — BaseRenderer 抽象接口（含 close 生命周期）、TextRenderer 默认实现、多通道/节流/续接设计
- `agent-adapters`: Agent 适配器 — HermesAdapter（SSE 流式）、OpenCodeAdapter（SSE + 状态机 + 权限 + 工具调用 + 流式踩坑修复）

### Modified Capabilities

（无 — 全新项目）

## Impact

- **新项目**: 全新 Python 包 `weixin_bot`
- **依赖**: httpx（异步 HTTP）、pydantic v2（数据校验）、pycryptodome（AES）、python-dotenv（配置）、qrcode（终端二维码）
- **参考**: nanobot（Python 通信层主参考）、QwenPaw（AES 密钥处理补充参考）、weixin-agent-sdk（协议规范交叉验证）
- **运行时**: Python 3.10+、无需公网 IP（长轮询模式）
- **范围**: 单进程单账号，微信当前仅支持 P2P 私聊
