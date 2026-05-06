# weixinbot 开发指南

## 环境准备

### 系统要求

- Python 3.10 或更高版本
- 支持 asyncio 的运行环境
- 稳定的网络连接（用于 ilink API 通信）

### 安装步骤

1. 克隆代码仓库：
```bash
git clone <repository-url>
cd weixinbot
```

2. 创建虚拟环境：
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows
```

3. 安装依赖（开发模式）：
```bash
pip install -e ".[dev]"
```

## 运行项目

### 命令行启动

安装后，直接使用命令：
```bash
weixinbot
```

或使用 Python 模块方式：
```bash
python -m weixin_bot
```

### 配置文件

创建 `.env` 文件在项目根目录：

```env
# 微信账号配置
WEIXIN_UIN=your_uin
WEIXIN_TOKEN=your_token

# 可选配置
LOG_LEVEL=INFO
DATA_DIR=~/.weixinbot
WHITELIST_USERS=wxid_xxx,wxid_yyy
```

也可以通过环境变量设置，优先级高于 `.env` 文件。

## 创建自定义机器人

### Echo Bot 示例

创建一个简单的回声机器人：

```python
# echo_bot.py
import asyncio
from weixinbot import WeixinBot
from weixinbot.messaging import IncomingEvent

bot = WeixinBot()

@bot.handler()
async def echo_handler(event: IncomingEvent):
    """回声处理器：重复用户发送的内容"""
    if event.content:
        await event.reply(f"你说：{event.content}")

if __name__ == "__main__":
    asyncio.run(bot.run())
```

运行：
```bash
python echo_bot.py
```

### 命令处理器示例

```python
from weixinbot.messaging import CommandRouter

@CommandRouter.register("/hello")
async def hello_command(event):
    await event.reply("你好！我是 weixinbot。")

@CommandRouter.register("/help")
async def help_command(event):
    help_text = """
可用命令：
/hello - 打招呼
/help - 显示帮助
/exit - 退出当前模式
    """
    await event.reply(help_text)
```

## 添加 Agent 适配器

Agent 适配器用于接入外部 AI 服务（如 OpenAI、Claude 等）。

### 实现适配器

```python
from weixinbot.modes import AgentAdapter, Session

class MyAIAdapter(AgentAdapter):
    def __init__(self, api_key: str):
        self.api_key = api_key
    
    async def create_session(self, user_id: str) -> Session:
        """创建新会话"""
        return Session(
            user_id=user_id,
            context={"messages": []}
        )
    
    async def send(self, session: Session, message: str) -> str:
        """发送消息并获取 AI 回复"""
        # 调用你的 AI 服务 API
        session.context["messages"].append({
            "role": "user", "content": message
        })
        
        # 这里调用实际的 AI API
        reply = await call_your_ai_api(
            self.api_key, 
            session.context["messages"]
        )
        
        session.context["messages"].append({
            "role": "assistant", "content": reply
        })
        return reply
    
    async def destroy_session(self, session: Session):
        """销毁会话，清理资源"""
        session.context.clear()
```

### 注册适配器

```python
from weixinbot.modes import ModeManager

# 创建适配器实例
my_adapter = MyAIAdapter(api_key="your-api-key")

# 注册到 ModeManager
mode_manager = ModeManager()
mode_manager.register_adapter("myai", my_adapter)

# 用户输入 /myai 命令时进入该模式
@CommandRouter.register("/myai")
async def enter_myai_mode(event):
    await mode_manager.enter_mode(event.user_id, "myai")
    await event.reply("已进入 MyAI 模式，直接发送消息开始对话。")
```

## 测试

### 运行测试

```bash
# 运行所有测试
pytest

# 运行特定测试文件
pytest tests/test_messaging.py

# 带覆盖率报告
pytest --cov=weixinbot --cov-report=html
```

### 测试依赖

- **pytest**：测试框架
- **pytest-asyncio**：支持异步测试
- **pytest-httpx**：模拟 HTTP 请求

### 异步测试示例

```python
import pytest
from weixinbot.messaging import IncomingEvent

@pytest.mark.asyncio
async def test_echo_handler():
    event = IncomingEvent(
        content="测试消息",
        from_user="wxid_test",
        msg_id="123"
    )
    
    # 模拟回复
    replies = []
    event.reply = lambda x: replies.append(x)
    
    await echo_handler(event)
    
    assert len(replies) == 1
    assert "测试消息" in replies[0]
```

### 模拟 HTTP 请求

```python
import pytest
from pytest_httpx import HTTPXMock

@pytest.mark.asyncio
async def test_api_call(httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url="https://ilinkai.weixin.qq.com/cgi-bin/getupdates",
        json={"errcode": 0, "data": {"item_list": []}}
    )
    
    # 你的测试代码
    result = await api.get_updates()
    assert result.errcode == 0
```

## 调试技巧

1. **启用 DEBUG 日志**：设置 `LOG_LEVEL=DEBUG` 查看详细请求/响应
2. **使用断点**：在关键位置添加 `import pdb; pdb.set_trace()`
3. **查看存储文件**：检查 `~/.weixinbot/logs/` 中的日志文件
4. **模拟消息**：使用测试脚本直接构造 `IncomingEvent` 进行调试
