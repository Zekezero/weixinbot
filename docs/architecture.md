# weixinbot 架构文档

## 项目概述

weixinbot 是一个基于 Python 3.10+ 的异步微信机器人框架。它使用微信 ilink API 进行通信，采用长轮询（long-polling）机制而非 webhook，确保在各类网络环境下都能稳定接收消息。

核心设计理念：
- **异步优先**：基于 asyncio 构建，支持高并发消息处理
- **模块化设计**：清晰的模块划分，易于扩展和维护
- **插件化渲染**：消息渲染与业务逻辑解耦
- **状态管理**：支持用户级别的有状态会话（Agent Mode）

## 模块结构

```
weixinbot/
├── config/          # 配置管理
│   ├── settings.py  # 全局配置
│   └── constants.py # 常量定义
├── errors/          # 异常定义
├── models/          # 数据模型
│   ├── message.py   # 消息模型
│   └── user.py      # 用户模型
├── client/          # HTTP 客户端封装
├── api/             # ilink API 封装
│   ├── auth.py      # 认证相关
│   ├── message.py   # 消息接口
│   └── cdn.py       # CDN 接口
├── auth/            # 登录认证
│   └── qrcode.py    # 二维码登录
├── monitor/         # 消息监听
│   └── longpoll.py  # 长轮询实现
├── messaging/       # 消息处理
│   ├── router.py    # 命令路由
│   ├── registry.py  # 处理器注册
│   └── renderer.py  # 消息渲染
├── cdn/             # CDN 媒体下载
├── media/           # 媒体处理
├── modes/           # Agent 模式
│   ├── manager.py   # 模式管理器
│   └── adapter.py   # 适配器基类
└── util/            # 工具函数
```

## 消息处理流程

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│   Monitor   │────▶│ dispatch_raw │────▶│    typing   │
│  (长轮询)    │     │  (原始分发)   │     │  (输入状态)  │
└─────────────┘     └──────────────┘     └──────┬──────┘
                                                │
                                                ▼
┌─────────────┐     ┌──────────────────────────────────────┐
│   Handler   │◀────│           IncomingEvent               │
│  (处理器)    │     │  (消息事件，包含 content/from_user等)  │
└──────┬──────┘     └──────────────────────────────────────┘
       │
       │     ┌───────────┐    ┌───────────┐    ┌───────────┐
       └───▶ │ whitelist │───▶│  commands │───▶│   mode    │
             │ (白名单)   │    │  (命令)   │    │ (Agent)   │
             └───────────┘    └───────────┘    └───────────┘
                                                        │
       ┌────────────────────────────────────────────────┘
       │
       ▼
┌─────────────┐     ┌─────────────┐
│ send_text   │     │    reply    │
│  (发送文本)  │     │   (回复)    │
└─────────────┘     └─────────────┘
```

处理流程说明：
1. **Monitor** 通过长轮询持续监听 ilink 服务器的消息推送
2. 收到消息后，**dispatch_raw** 将原始数据转换为内部格式
3. 发送 typing 状态，提示用户机器人正在输入
4. 创建 **IncomingEvent** 对象，封装消息内容和发送者信息
5. 进入分发管道：
   - **白名单过滤**：检查用户是否在允许列表中
   - **命令路由**：匹配以 `/` 开头的命令，由 CommandRouter 处理
   - **Agent 模式**：进入有状态会话，由 ModeManager 管理
   - **默认处理器**：由 HandlerRegistry 中的处理器处理
6. 最终通过 Renderer 渲染并发送回复

## 可插拔渲染器设计

渲染器负责将内部消息格式转换为微信支持的格式。

```
┌─────────────────┐
│  BaseRenderer   │◀────── 抽象基类 (ABC)
│   (渲染器基类)   │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌────────┐  ┌─────────────┐
│TextRenderer│  CardRenderer │
│(文本渲染器)│  │(卡片渲染器)   │
│ 默认实现  │  │   (未来)     │
└────────┘  └─────────────┘
```

**BaseRenderer** 定义了统一的接口：
- `render_text(content: str) -> dict`：渲染纯文本
- `render_markdown(content: str) -> dict`：渲染 Markdown
- `render_image(url: str) -> dict`：渲染图片

**TextRenderer** 是默认实现，将所有内容转换为微信文本消息格式。未来可扩展 **CardRenderer** 支持更丰富的卡片消息。

## Agent 模式架构

Agent 模式支持用户级别的有状态会话，适用于需要多轮交互的场景。

```
┌─────────────────┐
│   ModeManager   │◀────── 管理所有用户的会话状态
│   (模式管理器)   │
└────────┬────────┘
         │
         │ 创建/获取会话
         ▼
┌─────────────────┐
│   AgentAdapter  │◀────── 抽象适配器接口
│   (适配器基类)   │
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌────────┐  ┌────────┐
│OpenAI  │  │ Claude │
│Adapter │  │Adapter │
└────────┘  └────────┘
         │
         │ 发布事件
         ▼
┌─────────────────┐
│    EventBus     │◀────── 发布/订阅解耦
│    (事件总线)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Renderer     │◀────── 渲染输出
│    (渲染器)      │
└─────────────────┘
```

**ModeManager** 职责：
- 维护用户 ID 到 Agent 会话的映射
- 管理会话生命周期（创建、超时、销毁）
- 协调命令退出（如 `/exit` 命令退出 Agent 模式）

**AgentAdapter** 抽象接口：
- `create_session(user_id: str) -> Session`：创建新会话
- `send(session: Session, message: str) -> str`：发送消息并获取回复
- `destroy_session(session: Session)`：销毁会话

**EventBus** 提供发布/订阅机制，解耦 Agent 与渲染器，支持事件日志、消息拦截等功能。

## 存储布局

weixinbot 在 `~/.weixinbot/` 目录下存储运行时数据：

```
~/.weixinbot/
├── accounts/           # 账号数据
│   └── <uin>/         # 按微信 UIN 区分
│       ├── config.json    # 账号配置
│       ├── session.json   # 会话状态
│       └── qrcode.png     # 登录二维码
├── sync/              # 同步数据
│   └── <uin>/
│       ├── sync_buf       # 长轮询 sync buffer
│       └── checkpoint     # 同步检查点
└── logs/              # 日志文件
    └── weixinbot.log
```

**accounts/** 目录存储每个登录账号的独立数据，支持多账号运行。

**sync/** 目录存储长轮询所需的同步状态，包括：
- `sync_buf`：服务器返回的同步缓冲区，用于断线续传
- `checkpoint`：消息同步检查点，避免重复处理

**logs/** 目录存储运行日志，便于问题排查。

## 扩展点

1. **自定义命令**：使用 `@CommandRouter.register("/cmd")` 装饰器
2. **自定义处理器**：使用 `@HandlerRegistry.register` 装饰器
3. **自定义 Agent**：继承 `AgentAdapter` 实现特定 AI 服务接入
4. **自定义渲染器**：继承 `BaseRenderer` 实现新的消息格式
