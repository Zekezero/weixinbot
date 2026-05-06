# weixinbot — 通用 Python 微信机器人框架

基于微信 ilink API 的异步微信机器人框架，支持命令系统、Agent 模式和可插拔渲染器。

## 特性

- **装饰器命令系统**：使用 `@bot.command("name")` 快速定义命令
- **消息处理器**：使用 `@bot.on_message()` 注册消息回调
- **Agent 模式支持**：用户级别的有状态会话，支持多轮对话
- **可插拔渲染器**：BaseRenderer 抽象基类支持文本、卡片等多种消息格式
- **QR 扫码登录**：首次运行自动生成二维码，无需手动配置凭证
- **长轮询架构**：基于 ilink 长轮询，无需 webhook，网络适应性强
- **异步高并发**：基于 asyncio，支持高效处理大量消息

## 快速开始

### 安装

```bash
pip install weixin-bot
```

或从源码安装：

```bash
git clone https://github.com/user/weixinbot
cd weixinbot
pip install -e ".[dev]"
```

### 配置

创建 `.env` 文件（可选）：

```env
WEIXIN_STATE_DIR=~/.weixinbot
WEIXIN_LOG_LEVEL=INFO
```

首次运行时会自动弹出二维码，扫码登录即可。

### 5 分钟上手

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

运行：

```bash
python bot.py
```

扫码登录后，向机器人发送消息即可看到回声效果。

## 架构概览

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Monitor   │────▶│   WeixinBot │────▶│   Handler   │
│  (长轮询)    │     │  (主入口)    │     │  (处理器)   │
└─────────────┘     └──────┬──────┘     └──────┬──────┘
                           │                   │
        ┌──────────────────┼───────────────────┘
        │                  │
        ▼                  ▼
┌───────────────┐   ┌──────────────┐
│ CommandRouter │   │  ModeManager │
│   (命令路由)   │   │ (Agent 管理)  │
└───────┬───────┘   └──────┬───────┘
        │                  │
        │           ┌──────┴──────┐
        │           │   Renderer   │
        │           │   (渲染器)   │
        │           └─────────────┘
        │                  │
        ▼                  ▼
┌───────────────┐   ┌──────────────┐
│  AgentAdapter │   │   EventBus   │
│  (适配器接口)  │   │   (事件总线)  │
└───────────────┘   └──────────────┘
```

## 内置指令

- `/help` — 显示帮助信息
- `/health` — 健康检查
- `/ping` — 测试连通性
- `/echo <text>` — 回声测试
- `/exit` — 退出当前模式
- `/new` — 当前模式下新建会话
- `/modes` — 列出可用模式

## 示例

### Echo Bot（回声机器人）

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

### 自定义指令

```python
from weixin_bot.models import WeixinMsgDTO

@bot.command("hello", description="打招呼")
async def cmd_hello(msg: WeixinMsgDTO, bot: WeixinBot) -> None:
    await bot.send_text(msg.session_id, f"你好，{msg.from_}！")
```

## 文档

- [架构文档](docs/architecture.md) — 项目架构和模块说明
- [开发指南](docs/development.md) — 开发环境搭建和扩展开发

## 许可证

MIT License
