# weixinbot — 通用 Python 微信机器人框架

基于微信 ilink API 的异步微信机器人框架，支持命令系统、Agent 模式和可插拔渲染器。

## 特性

- **装饰器命令系统**：使用 `@CommandRouter.register("/cmd")` 快速定义命令
- **Agent 模式支持**：用户级别的有状态会话，支持多轮对话
- **可插拔渲染器**：BaseRenderer ABC 支持文本、卡片等多种消息格式
- **CDN 媒体处理**：自动下载解密图片、语音、视频等媒体文件
- **长轮询架构**：基于 ilink 长轮询，无需 webhook，网络适应性强
- **异步高并发**：基于 asyncio，支持高效处理大量消息

## 快速开始

### 安装

```bash
pip install weixinbot
```

### 配置

创建 `.env` 文件：

```env
WEIXIN_UIN=your_uin
WEIXIN_TOKEN=your_token
```

或使用二维码登录（首次运行自动生成）。

### 5 分钟上手

```python
import asyncio
from weixinbot import WeixinBot

bot = WeixinBot()

@bot.handler()
async def echo(event):
    await event.reply(f"收到：{event.content}")

asyncio.run(bot.run())
```

运行：

```bash
python bot.py
```

## 架构概览

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Monitor   │────▶│   Router    │────▶│   Handler   │
│  (长轮询)    │     │  (命令路由)  │     │  (处理器)   │
└─────────────┘     └──────┬──────┘     └──────┬──────┘
                           │                   │
                    ┌──────┴──────┐           │
                    │  ModeManager │◀──────────┘
                    │ (Agent 管理) │
                    └──────┬──────┘
                           │
                    ┌──────┴──────┐
                    │   Renderer   │
                    │   (渲染器)   │
                    └─────────────┘
```

## 示例

### Echo Bot（回声机器人）

```python
@bot.handler()
async def echo(event):
    await event.reply(event.content)
```

### OpenAI Bot（AI 对话）

```python
from weixinbot.modes import ModeManager
from weixinbot.adapters import OpenAIAdapter

mode_mgr = ModeManager()
mode_mgr.register_adapter("gpt", OpenAIAdapter(api_key="sk-xxx"))

@CommandRouter.register("/chat")
async def chat(event):
    await mode_mgr.enter_mode(event.user_id, "gpt")
    await event.reply("已进入 AI 对话模式")
```

## 文档

- [架构文档](docs/architecture.md) — 项目架构和模块说明
- [ilink 协议](docs/ilink-protocol.md) — ilink API 详细参考
- [开发指南](docs/development.md) — 开发环境搭建和扩展开发

## 许可证

MIT License
