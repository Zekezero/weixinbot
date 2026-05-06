# 开发指南

本文档介绍如何搭建开发环境、运行机器人以及扩展功能。

## 环境要求

- Python 3.10+
- Git

## 开发环境搭建

### 1. 克隆仓库

```bash
git clone https://github.com/user/weixinbot
cd weixinbot
```

### 2. 创建虚拟环境

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -e ".[dev]"
```

这会安装核心依赖和开发依赖（pytest、ruff、mypy 等）。

### 4. 配置环境变量

复制示例配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件，根据需要配置：

```env
# 微信 ilink 配置
WEIXIN_STATE_DIR=~/.weixinbot
WEIXIN_LOG_LEVEL=INFO

# Hermes Agent（可选）
HERMES_API_KEY=your-hermes-api-key
HERMES_BASE_URL=https://api.hermes.example.com

# OpenCode Agent（可选）
OPENCODE_BASE_URL=http://localhost:29107
OPENCODE_PROJECT_DIR=/path/to/project

# OpenAI Agent（示例用）
OPENAI_API_KEY=sk-xxx
OPENAI_MODEL=gpt-4o
OPENAI_BASE_URL=https://api.openai.com/v1

# 渲染器配置
WEIXIN_RENDERER_TYPE=text
WEIXIN_RENDERER_PUSH_INTERVAL=3.0
WEIXIN_RENDERER_PUSH_MIN_CHARS=2000
WEIXIN_RENDERER_MAX_MESSAGE_CHARS=3000
```

## 运行机器人

### 方式1: 模块运行

```bash
python -m weixin_bot
```

### 方式2: 命令行入口

```bash
weixinbot
```

### 方式3: 运行示例

```bash
# 回声机器人
python examples/echo_bot.py

# OpenAI 对话机器人
python examples/openai_bot.py
```

首次运行会显示二维码，使用微信扫码登录。

## 项目结构

```
weixinbot/
├── src/weixin_bot/      # 核心源码
├── examples/            # 示例代码
├── tests/               # 测试代码
├── docs/                # 文档
├── pyproject.toml       # 项目配置
└── .env.example         # 环境变量示例
```

## 编写 Echo Bot

最简单的机器人示例：

```python
from weixin_bot.bot import WeixinBot
from weixin_bot.config import WeixinBotConfig
from weixin_bot.models import IncomingEvent

bot = WeixinBot(WeixinBotConfig.from_env())


@bot.on_message()
async def echo(event: IncomingEvent) -> None:
    msg = event.as_message()
    await bot.reply(event, f"你说: {msg.text}")


if __name__ == "__main__":
    bot.run()
```

## 添加自定义指令

```python
# 接在上面的 echo bot 代码之后（已有 bot 实例）
from weixin_bot.models import WeixinMsgDTO

@bot.command("hello", description="打招呼")
async def cmd_hello(msg: WeixinMsgDTO, bot) -> None:
    await bot.send_text(msg.session_id, f"你好，{msg.from_}！")
```

指令参数：

- `name`: 指令名称（不含 `/` 前缀）
- `description`: 帮助文本中显示的描述
- `p2p_only`: 仅私聊可用
- `group_only`: 仅群聊可用（当前微信不支持）
- `aliases`: 别名列表

## 添加新的 Agent 适配器

实现 `AgentAdapter` 抽象类：

```python
from weixin_bot.modes.adapter import AgentAdapter, MessageContext
from weixin_bot.modes.events import EventBus, ResponseStart, ResponseChunk, ResponseEnd

class MyAdapter(AgentAdapter):
    name = "myagent"
    display_name = "My Agent"

    def __init__(self, bus: EventBus) -> None:
        super().__init__(bus)
        self._sessions: dict[str, str] = {}

    async def create_session(self) -> str:
        # 创建会话，返回 session_id
        import uuid
        session_id = str(uuid.uuid4())
        self._sessions[session_id] = "active"
        return session_id

    async def send(
        self,
        session_id: str,
        message: str,
        context: MessageContext,
        *,
        user_id: str,
    ) -> str:
        # 发送消息到 Agent
        # 通过 EventBus 发射流式事件
        await self._bus.emit(ResponseStart(user_id=user_id, mode=self.name,
                                           session_id=session_id, chat_id=context.chat_id))

        # 模拟流式响应
        response_text = f"收到: {message}"
        await self._bus.emit(ResponseChunk(user_id=user_id, mode=self.name,
                                           session_id=session_id, text=response_text))

        await self._bus.emit(ResponseEnd(user_id=user_id, mode=self.name,
                                         session_id=session_id, full_text=response_text))
        return response_text

    async def destroy_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)
```

注册适配器（参考 `app.py` 中的 `_register_adapters`）：

```python
from weixin_bot.bot import WeixinBot
from weixin_bot.config import WeixinBotConfig
from weixin_bot.models import WeixinMsgDTO
from weixin_bot.modes.manager import ModeManager
from weixin_bot.modes.events import EventBus
from weixin_bot.modes.renderer import RendererConfig, TextRenderer

# 创建完整的 bot 实例（含渲染器）
bus = EventBus()
mode_manager = ModeManager(bus)
config = WeixinBotConfig.from_env()
bot = WeixinBot(config, mode_manager=mode_manager)

# 初始化渲染器（必须，否则 Agent 的流式事件不会被发送到微信）
async def _send_text(chat_id: str, text: str) -> None:
    await bot.send_text(chat_id, text)

renderer = TextRenderer(_send_text, bus, RendererConfig())

# 注册适配器
my_adapter = MyAdapter(bus)
mode_manager.register_adapter(my_adapter)

@bot.command("myagent", description="进入 MyAgent 模式")
async def cmd_myagent(msg: WeixinMsgDTO, bot) -> None:
    if mode_manager.is_in_mode(msg.from_):
        await bot.send_text(msg.session_id, "请先 /exit 退出当前模式")
        return
    sid = await mode_manager.enter_mode(msg.from_, "myagent")
    await bot.send_text(msg.session_id, f"已进入 MyAgent 模式 (会话 #{sid[:8]})")
```

## 测试

### 运行测试

```bash
pytest
```

### 测试结构

```python
import pytest
from weixin_bot.commands import CommandRouter
from weixin_bot.models import WeixinMsgDTO


@pytest.fixture
def router():
    return CommandRouter()


@pytest.mark.asyncio
async def test_command_registration(router):
    @router.command("test", description="测试指令")
    async def cmd_test(msg, bot):
        await bot.send_text(msg.session_id, "ok")

    assert "test" in router.registered_commands
```

### 常用测试模式

Mock 消息对象：

```python
from unittest.mock import AsyncMock

mock_msg = WeixinMsgDTO(
    from_="user123",
    session_id="session456",
    text="/test hello",
    is_p2p=True,
    is_group=False,
)

mock_bot = AsyncMock()
mock_bot.send_text = AsyncMock()

await router.try_handle(mock_msg, mock_bot)
mock_bot.send_text.assert_called_once()
```

## 代码规范

使用 ruff 进行代码检查和格式化：

```bash
# 检查
ruff check src/

# 格式化
ruff format src/

# 类型检查
mypy src/
```

配置位于 `pyproject.toml`：

```toml
[tool.ruff]
target-version = "py310"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP"]
```

## 调试技巧

### 启用调试日志

```env
WEIXIN_LOG_LEVEL=DEBUG
```

或在代码中：

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### 查看状态文件

```bash
# 账号凭证
ls ~/.weixinbot/accounts/
cat ~/.weixinbot/accounts/{account_id}.json

# 同步缓冲区
ls ~/.weixinbot/sync/
```

## 常见问题

### 扫码后无响应

检查网络连接，确保能访问 ilink API 服务器。

### 消息重复处理

WeixinMonitor 内置了消息去重（LRU 缓存，30 分钟 TTL），通常无需处理。

### 会话过期

出现 `errcode=-14` 时会自动暂停 1 小时，需要重新扫码登录。

## 发布新版本

1. 更新 `pyproject.toml` 中的版本号
2. 更新 `CHANGELOG.md`
3. 创建 git tag
4. 构建并上传

```bash
python -m build
python -m twine upload dist/*
```
