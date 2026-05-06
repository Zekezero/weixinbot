# 架构文档

本文档详细说明 weixinbot 的模块结构、消息流和核心接口。

## 模块结构

```
src/weixin_bot/
├── __init__.py
├── __main__.py          # 模块入口: python -m weixin_bot
├── app.py               # 生产机器人入口，create_bot() 工厂
├── bot.py               # WeixinBot 主类
├── config.py            # WeixinBotConfig 配置类
├── monitor.py           # WeixinMonitor 长轮询消息循环
├── commands.py          # CommandRouter 指令路由器
├── handler.py           # HandlerRegistry 事件处理器注册表
├── models.py            # Pydantic 数据模型
├── api.py               # WeixinAPI 封装
├── client.py            # WeixinClient HTTP 客户端
├── auth.py              # QR 登录和凭证管理
├── messaging.py         # 消息构建和解析工具
├── errors.py            # 异常定义
├── cdn/                 # CDN 媒体加解密
│   ├── __init__.py      # AES-128-ECB 核心函数 + 密钥解析
│   ├── upload.py        # CDN 上传管道
│   └── download.py      # CDN 下载 + 解密管道
├── media/               # 媒体文件处理
│   ├── __init__.py
│   ├── download.py      # 统一媒体下载入口（IMAGE/VOICE/FILE/VIDEO）
│   ├── mime.py          # 文件头魔数 MIME 检测
│   └── silk_transcode.py # SILK→WAV 音频转码（可选）
├── modes/               # Agent 模式系统
│   ├── __init__.py
│   ├── adapter.py       # AgentAdapter 抽象接口
│   ├── events.py        # EventBus 事件总线
│   ├── manager.py       # ModeManager 模式管理器
│   ├── renderer.py      # BaseRenderer / TextRenderer
│   └── adapters/        # 具体适配器实现
│       ├── __init__.py
│       ├── opencode.py
│       └── hermes.py
└── util/                # 工具函数
    ├── __init__.py
    └── logger.py
```

## 消息处理流程

消息从接收到回复的完整流程：

```
1. WeixinMonitor.start() 长轮询获取消息
   └─▶ _poll_once() 调用 getUpdates
       └─▶ _handle_message() 去重后分发

2. WeixinBot._dispatch_raw(raw_msg)
   └─▶ 跳过 bot 自己发送的消息 (msg_type == 2)
   └─▶ 构建 WeixinMessage → IncomingEvent
   └─▶ 调用 _dispatch(event)

3. WeixinBot._dispatch(event) 处理管道
   ├─▶ 白名单检查 (config.allowed_users)
   ├─▶ CommandRouter.try_handle(msg, bot)
   │   └─▶ 匹配 /xxx 指令，执行 handler
   ├─▶ ModeManager.try_forward(event)
   │   └─▶ 用户在模式中？转发给 AgentAdapter
   └─▶ HandlerRegistry.dispatch(event)
       └─▶ 执行注册的 @bot.on_message() 处理器
```

## 核心接口

### WeixinBot 主类

位于 `bot.py`，一站式机器人入口。

```python
class WeixinBot:
    def __init__(self, config: WeixinBotConfig, mode_manager: ModeManager | None = None)

    # 装饰器 API
    def command(self, name: str, *, description: str = "", p2p_only: bool = False, ...)
    def on_message(self, *, msg_types: list[int] | None = None, p2p_only: bool = False, ...)
    def on_recall(self)

    # 消息发送
    async def send_text(self, receiver: str, content: str) -> None
    async def reply(self, event: IncomingEvent, content: str) -> None

    # 生命周期
    async def start(self) -> None      # 异步启动（非阻塞）
    async def stop(self) -> None       # 停止机器人
    async def wait(self) -> None       # 等待停止
    def run(self) -> None              # 阻塞式启动（同步入口）
```

### CommandRouter 指令路由

位于 `commands.py`，处理 `/xxx` 格式的命令。

```python
class CommandRouter:
    def command(self, name: str, *, description: str = "", p2p_only: bool = False,
                group_only: bool = False, aliases: list[str] | None = None)
        # 返回装饰器，用于注册指令处理函数

    async def try_handle(self, msg: WeixinMsgDTO, bot: BotLike) -> bool
        # 尝试匹配并执行指令，返回是否匹配成功
```

### HandlerRegistry 事件处理器

位于 `handler.py`，处理非指令消息。

```python
class HandlerRegistry:
    def on(self, event_type: str, *, filter_fn: MessageFilter | None = None)
    def on_message(self, *, msg_types: list[MsgType | int] | None = None,
                   p2p_only: bool = False, group_only: bool = False)
    def on_recall(self)

    async def dispatch(self, event: IncomingEvent) -> None
```

### AgentAdapter 抽象接口

位于 `modes/adapter.py`，定义 Agent 后端适配器协议。

```python
class AgentAdapter(ABC):
    name: str           # 适配器标识，如 "opencode"
    display_name: str   # 显示名称，如 "OpenCode Agent"

    def __init__(self, bus: EventBus) -> None

    @abstractmethod
    async def create_session(self) -> str:
        # 创建新会话，返回 session_id

    @abstractmethod
    async def send(self, session_id: str, message: str, context: MessageContext,
                   *, user_id: str) -> str:
        # 发送消息到 Agent，流式通过 EventBus 发射事件
        # 返回完整响应文本

    @abstractmethod
    async def destroy_session(self, session_id: str) -> None:
        # 销毁指定会话

    async def list_sessions(self) -> list[SessionInfo]:
        # 可选：列出历史会话
```

### EventBus 事件总线

位于 `modes/events.py`，发布/订阅模式的事件系统。

```python
class EventBus:
    def on(self, event_type: type, handler: EventHandler) -> None
    async def emit(self, event: ModeEvent) -> None
```

事件类型：

- `ModeEntered` — 用户进入模式
- `ModeExited` — 用户退出模式
- `ResponseStart` — Agent 开始响应
- `ResponseChunk` — Agent 响应的一个文本片段
- `ResponseEnd` — Agent 响应结束
- `ResponseError` — Agent 响应出错

### BaseRenderer 渲染器接口

位于 `modes/renderer.py`，事件驱动的输出渲染。

```python
class BaseRenderer(ABC):
    def __init__(self, send_fn: SendFunction, bus: EventBus, config: RendererConfig)

    @abstractmethod
    async def on_response_start(self, event: ResponseStart) -> None

    @abstractmethod
    async def on_response_chunk(self, event: ResponseChunk) -> None

    @abstractmethod
    async def on_response_end(self, event: ResponseEnd) -> None

    @abstractmethod
    async def on_response_error(self, event: ResponseError) -> None
```

`TextRenderer` 是默认实现，将流式响应转为分段文本消息。

### ModeManager 模式管理器

位于 `modes/manager.py`，维护用户会话与转发。

```python
class ModeManager:
    def __init__(self, bus: EventBus)

    def register_adapter(self, adapter: AgentAdapter) -> None
    def get_adapter(self, name: str) -> AgentAdapter | None
    def is_in_mode(self, user_id: str) -> bool

    async def enter_mode(self, user_id: str, mode_name: str,
                         session_id: str | None = None) -> str
    async def exit_mode(self, user_id: str) -> None
    async def new_session(self, user_id: str) -> str
    async def try_forward(self, event: IncomingEvent) -> bool
```

### WeixinBotConfig 配置

位于 `config.py`，从 `.env` 文件和环境变量加载配置。

```python
@dataclass(frozen=True)
class WeixinBotConfig:
    state_dir: str = ""
    log_level: str = "INFO"
    hermes_api_key: str = ""
    hermes_base_url: str = ""
    opencode_base_url: str = "http://localhost:29107"
    opencode_project_dir: str = ""
    renderer_type: str = "text"
    renderer_push_interval: float = 3.0
    renderer_push_min_chars: int = 2000
    renderer_max_message_chars: int = 3000
    allowed_users: list[str] = field(default_factory=list)

    @classmethod
    def from_env(cls, dotenv_path: str | Path | None = None) -> WeixinBotConfig

    @property
    def resolved_state_dir(self) -> Path  # 默认 ~/.weixinbot/
```

环境变量包含 `WEIXIN_*`（微信/渲染器/流式卡片）以及 `HERMES_*`、`OPENCODE_*`（Agent 适配器配置）。

### WeixinMonitor 消息监控

位于 `monitor.py`，长轮询消息循环。

```python
class WeixinMonitor:
    def __init__(self, client: WeixinClient, state_dir: Path,
                 on_message: Callable[[dict[str, Any]], Awaitable[None]])

    async def start(self) -> None   # 启动长轮询循环
    def stop(self) -> None          # 停止循环

    def get_context_token(self, user_id: str) -> str
    def set_context_token(self, user_id: str, token: str) -> None

    async def start_typing(self, user_id: str) -> None
    async def stop_typing(self, user_id: str) -> None
```

## 存储布局

状态数据默认存储在 `~/.weixinbot/`：

```
~/.weixinbot/
├── accounts.json              # 账号索引
├── accounts/
│   └── {normalized_id}.json   # 账号凭证 (token, baseUrl, userId)，文件名经规范化处理
└── sync/
    └── {normalized_id}.buf    # 同步缓冲区 (get_updates_buf)
```

> 注：`normalized_id` = `account_id.strip().lower().replace("@", "-").replace(".", "-")`

## 启动方式

```bash
# 方式1: 模块运行
python -m weixin_bot

# 方式2: 命令行入口 (安装后)
weixinbot

# 方式3: 直接运行示例
python examples/echo_bot.py
```

## 登录流程

1. 首次启动时检查 `~/.weixinbot/accounts/` 目录
2. 如存在有效凭证，直接加载使用
3. 如无有效凭证，触发 QR 扫码登录
4. 扫码成功后保存凭证到 `accounts/{accountId}.json`
5. 后续启动自动加载已保存的凭证

会话过期（errcode=-14）时暂停轮询 1 小时并提示用户重新扫码登录（需人工重启触发登录流程）。
