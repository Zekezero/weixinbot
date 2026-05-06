## Context

我们正在构建 weixinbot — 一个通用 Python 微信机器人框架。

**现有资产**：
- **已验证的内部框架** — Python 3.10+ 异步实现。其 CommandRouter / HandlerRegistry / AgentAdapter / ModeManager / EventBus 经过生产验证，架构合理
- **weixin-agent-sdk** — TypeScript 微信 ilink 协议实现，包含完整的 QR 登录、长轮询、CDN 加解密、媒体处理
- **已有 Python 参考** — nanobot (HKUDS)、QwenPaw (agentscope-ai)、hermes-wechat (RongleCat) 等已实现 Python 版微信 ilink 通信

**约束**：
- 微信 ilink API 仅支持 P2P 私聊（当前无群聊能力）
- 微信无卡片消息、无富文本、无 @人能力（当前）
- 微信用长轮询（非 Webhook），无需公网 IP
- 微信 CDN 媒体传输使用 AES-128-ECB 加密

## Goals / Non-Goals

**Goals:**
- 构建一个通用微信机器人框架，采用可扩展的架构设计
- 指令系统、事件路由、Agent 模式管理完整支持
- Renderer 采用可插拔抽象设计 — 默认 TextRenderer，未来微信开放卡片能力后可快速接入 CardRenderer
- 复用流式输出的最佳实践（包括生产环保修复：竞态保护、乱序处理、超时重连等）
- 产出完整 docs/ 文档体系（架构、协议、开发指南）

**Non-Goals:**
- 不做特定平台适配（不同框架独立实现）
- 不做微信群聊能力（ilink API 当前不支持）
- 不做微信公众号 / 企业微信对接（不同协议体系）
- 不做跨平台抽象层（各框架保持独立设计）

## Decisions

### D1: Python 复用现有 ilink 实现，而非从 TypeScript 翻译

**选择**: 参考 nanobot / QwenPaw 的 Python ilink 实现来构建通信层
**替代方案**: 从 weixin-agent-sdk 的 TypeScript 逐行翻译
**理由**: 已有多个经过验证的 Python 实现，直接参考可避免 TS→Python 翻译的边界情况遗漏。weixin-agent-sdk 的协议规范文档作为对照验证。

### D2: 框架层模块直接复用现有代码

**选择**: commands.py / handler.py / modes/adapter.py / modes/events.py 直接复制，manager.py 微调类型
**替代方案**: 全部重写
**理由**: 这些模块已被经分析确认，与特定平台的耦合程度低。直接复用节省 ~60% 框架层工作量。

### D3: Renderer 可插拔抽象设计

**选择**: 定义 `BaseRenderer` ABC，通过 EventBus 事件驱动。默认 `TextRenderer` 实现分段文本发送。
**替代方案**: 硬编码文本发送，未来再重构
**理由**: 已有的流式渲染实现展示了卡片渲染的完整能力。微信当前不支持卡片，但 ilink API 在迭代中。可插拔设计使未来接入 CardRenderer 只需新增一个类，无需改动框架。

**BaseRenderer 接口设计**:
```python
class BaseRenderer(ABC):
    def __init__(self, send_fn: SendFunction, bus: EventBus, config: RendererConfig):
        # 订阅 EventBus: ResponseStart/Chunk/End/Error
        bus.on(ResponseStart, self._handle_start)
        bus.on(ResponseChunk, self._handle_chunk)
        bus.on(ResponseEnd, self._handle_end)
        bus.on(ResponseError, self._handle_error)

    @abstractmethod
    async def _handle_start(self, event): ...
    @abstractmethod
    async def _handle_chunk(self, event): ...
    @abstractmethod
    async def _handle_end(self, event): ...
    @abstractmethod
    async def _handle_error(self, event): ...
```

**TextRenderer 行为**:
- ResponseStart: 记录 user_id → chat_id 映射
- ResponseChunk: 累积到 buffer，按时间间隔（默认 3s）或字符阈值（默认 2000 字）分段发送
- ResponseEnd: flush 剩余 buffer，按 3000 字切分发送
- ResponseError: 发送错误文本

**未来 CardRenderer**（微信开放后）:
- 同样订阅 EventBus 事件
- ResponseStart: 创建卡片消息
- ResponseChunk: 更新卡片内容（实时）
- ResponseEnd: finalize 卡片
- 多通道、续接、节流等已验证的设计理念可直接迁移

### D4: 通信层架构 — Monitor + Client + Auth 三层分离

**选择**:
```
WeixinMonitor (长轮询循环)
  → WeixinClient (HTTP 请求 + headers + 重试)
    → WeixinAuth (QR 登录 + Token 管理 + 账号持久化)
```
**理由**: 实现清晰的三层分离架构。每层职责单一，可独立测试。

### D5: 流式输出最佳实践完整复用

**选择**: 复用成熟的 SSE 客户端、事件分类、工具格式化、竞态保护、abort 机制
**替代方案**: 只复用接口，重写实现
**理由**: 流式输出的 SSE 处理有多个生产级踩坑问题（已文档记录），包括竞态条件、乱序 chunk、权限交互、abort 中断等。这些修复代码是项目最有价值的沉淀，必须保留。

### D6: 项目结构

```
weixinbot/
├── pyproject.toml
├── .env.example
├── README.md
├── docs/
│   ├── architecture.md          # 架构设计文档
│   ├── ilink-protocol.md        # 微信 ilink 协议规范
│   └── development.md           # 开发指南
├── src/weixin_bot/
│   ├── __init__.py
│   ├── __main__.py
│   ├── app.py                   # create_bot() 入口
│   ├── bot.py                   # WeixinBot 主类
│   ├── config.py                # WeixinBotConfig
│   ├── errors.py                # 异常层级
│   ├── models.py                # Pydantic 模型
│   ├── commands.py              # CommandRouter (复用)
│   ├── handler.py               # HandlerRegistry (复用)
│   ├── auth.py                  # QR 登录 + Token 管理
│   ├── client.py                # WeixinClient HTTP 客户端
│   ├── monitor.py               # 长轮询 getUpdates 循环
│   ├── api.py                   # 微信 API 封装
│   ├── cdn/
│   │   ├── __init__.py
│   │   ├── aes_ecb.py           # AES-128-ECB 加解密
│   │   ├── upload.py            # CDN 上传
│   │   └── download.py          # CDN 下载 + 解密
│   ├── media/
│   │   ├── __init__.py
│   │   ├── download.py          # 媒体下载统一入口
│   │   ├── mime.py              # MIME 检测
│   │   └── silk_transcode.py    # SILK → WAV
│   ├── modes/
│   │   ├── __init__.py
│   │   ├── adapter.py           # AgentAdapter ABC (复用)
│   │   ├── manager.py           # ModeManager (微调)
│   │   ├── events.py            # EventBus (复用)
│   │   ├── renderer.py          # BaseRenderer + TextRenderer
│   │   └── adapters/
│   │       ├── __init__.py
│   │       ├── hermes.py        # HermesAdapter (适配)
│   │       └── opencode.py      # OpenCodeAdapter (适配)
│   └── util/
│       ├── __init__.py
│       ├── logger.py
│       ├── random.py
│       └── redact.py
├── examples/
│   ├── echo_bot.py
│   └── openai_bot.py
└── tests/
    └── ...
```

## Risks / Trade-offs

**[微信 API 变动]** → ilink API 是非公开协议，可能随时变更
- 缓解: 通信层集中在 client.py + api.py，变更影响面可控

**[参考实现质量]** → 开源参考实现的代码可能有未发现的 bug
- 缓解: 同时参考 weixin-agent-sdk（TS）协议规范做交叉验证

**[Renderer 过度设计]** → 抽象接口可能比微信实际需要的复杂
- 缓解: BaseRenderer 只定义 4 个事件处理方法（start/chunk/end/error），TextRenderer 实现简单直接。抽象成本极低，收益在未来

**[OpenCode 适配器兼容性]** → 流式处理适配器可能依赖特定框架行为
- 缓解: 已经分析确认，标记了所有平台耦合点。改动集中在 context 注入和会话映射，核心 SSE/工具格式化代码无需变更
