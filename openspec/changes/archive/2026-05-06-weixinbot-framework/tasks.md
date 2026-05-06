## 1. 项目初始化

- [x] 1.1 创建 pyproject.toml（包名 weixin-bot, console_scripts 入口 weixinbot, 依赖: httpx, pydantic>=2, cryptography, python-dotenv, qrcode）
- [x] 1.2 创建 src/weixin_bot/__init__.py 和 __main__.py 入口
- [x] 1.3 创建 .env.example 配置模板
- [x] 1.4 创建 .gitignore（Python 标准 + .env + __pycache__ + .venv + *.pyc）

## 2. 配置与错误模块

- [x] 2.1 创建 config.py — WeixinBotConfig dataclass，from_env() 加载 WEIXIN_* 和 HERMES_*/OPENCODE_* 配置
- [x] 2.2 创建 errors.py — WeixinError / AuthError / ApiError / CdnError 异常层级

## 3. 数据模型（models.py）

- [x] 3.1 创建微信协议枚举: MessageItemType(TEXT=1,IMAGE=2,VOICE=3,FILE=4,VIDEO=5), MessageType(USER=1,BOT=2), MessageState(NEW=0,GENERATING=1,FINISH=2)
- [x] 3.2 创建入站消息 Pydantic 模型: WeixinMessage, MessageItem, TextItem, ImageItem, VoiceItem, FileItem, VideoItem, CDNMedia, RefMessage
- [x] 3.3 创建出站消息模型: SendMessageReq, GetUpdatesReq/Resp, GetUploadUrlReq/Resp, GetConfigReq/Resp
- [x] 3.4 创建框架事件模型: IncomingEvent（与 HandlerRegistry 对接）, WeixinMsgDTO（与 CommandRouter 对接，需实现 text/session_id/from_/is_p2p/is_group 属性）
- [x] 3.5 创建事件类型枚举: EventType（P2P_MESSAGE 等），对齐 HandlerRegistry 需要的字符串 key

## 4. 工具模块（util/）

- [x] 4.1 创建 util/logger.py — 结构化 JSON 日志（参考已验证框架 logging 模式）
- [x] 4.2 创建 util/random.py — 生成 client_id 和 filekey
- [x] 4.3 创建 util/redact.py — Token/URL 脱敏工具

## 5. 微信 HTTP 客户端（client.py + api.py）

- [x] 5.1 创建 client.py — WeixinClient：httpx.AsyncClient 封装，标准请求头（Authorization, AuthorizationType, X-WECHAT-UIN, Content-Type），超时管理，base_info 注入
- [x] 5.2 创建 api.py — 封装所有 ilink API 端点: get_updates(), send_message(), get_upload_url(), get_config(), send_typing(), get_bot_qrcode(), get_qrcode_status()

## 6. 认证模块（auth.py）

- [x] 6.1 实现 QR 码登录流程: get_bot_qrcode → 终端渲染 → poll get_qrcode_status → 处理 wait/scaned/confirmed/expired/scaned_but_redirect 状态
- [x] 6.2 实现 IDC 重定向: scaned_but_redirect 时切换 API 基础 URL
- [x] 6.3 实现 QR 码过期自动刷新（最多 3 次）
- [x] 6.4 实现凭证持久化: 保存到 ~/.weixinbot/accounts/{accountId}.json（0o600 权限）
- [x] 6.5 实现凭证加载: 启动时检查本地凭证，有效则跳过扫码
- [x] 6.6 实现 is_logged_in() 和 logout() 公开函数

## 7. CDN 加解密模块（cdn/）

- [x] 7.1 创建 cdn/aes_ecb.py — AES-128-ECB 加密/解密函数，PKCS7 填充/去填充
- [x] 7.2 创建 cdn/upload.py — CDN 上传管道: 读取文件 → MD5 → 生成 AES 密钥 → 加密 → getUploadUrl → POST 密文 → 解析 x-encrypted-param
- [x] 7.3 创建 cdn/download.py — CDN 下载管道: 构建下载 URL → 下载密文 → 解析 AES 密钥（支持两种编码格式） → 解密

## 8. 媒体处理模块（media/）

- [x] 8.1 创建 media/download.py — 统一媒体下载入口: 根据 MessageItemType 路由到对应处理（IMAGE/VOICE/FILE/VIDEO）
- [x] 8.2 创建 media/mime.py — 文件头魔数 MIME 检测
- [x] 8.3 创建 media/silk_transcode.py — 可选 SILK→WAV 转码（尝试导入 silk 库，不可用则降级）

## 9. 长轮询消息循环（monitor.py）

- [x] 9.1 实现 WeixinMonitor 类: 异步循环调用 getUpdates，参数管理（get_updates_buf, timeout_ms）
- [x] 9.2 实现断点续传: 从 ~/.weixinbot/sync/{accountId}.buf 加载/保存 get_updates_buf
- [x] 9.3 实现重试逻辑: 正常超时立即重试，服务端错误 2s 重试，连续 3 次失败 30s 退避
- [x] 9.4 实现会话过期处理: errcode=-14 → 暂停 1 小时 + 日志提示重新登录
- [x] 9.5 实现 Typing 指示器: 收到消息时发送 typing(status=1)，每 10s 刷新，处理完成发送 typing(status=2)

## 10. 消息处理管道

- [x] 10.1 实现入站消息解析: WeixinMessage → 提取文本/媒体 → 构建 IncomingEvent
- [x] 10.2 实现出站文本消息构建: markdown_to_plaintext() + SendMessageReq 组装 + context_token 回传
- [x] 10.3 实现出站媒体消息: 本地路径 → CDN 上传 → 构建 ImageItem/VideoItem/FileItem → 发送
- [x] 10.4 实现 context_token 内存缓存: accountId:userId → token 映射

## 11. 框架层 — 直接复用

- [x] 11.1 从已验证框架复制 commands.py → weixin_bot/commands.py（更新 import 路径）
- [x] 11.2 从已验证框架复制 handler.py → weixin_bot/handler.py（更新 import 路径 + EventType 映射）
- [x] 11.3 从已验证框架复制 modes/adapter.py → weixin_bot/modes/adapter.py（零修改）
- [x] 11.4 从已验证框架复制 modes/events.py → weixin_bot/modes/events.py（零修改）

## 12. 框架层 — 适配

- [x] 12.1 适配 modes/manager.py: 将 MsgDTO 替换为 WeixinMsgDTO Protocol，更新 _build_context() 中的属性访问
- [x] 12.2 适配 modes/adapters/hermes.py: 去除内部平台 context 注入（第76-80行），更新 config import，保留 SSE 解析逻辑
- [x] 12.3 适配 modes/adapters/opencode.py: 替换内部平台映射 → _oc_to_wechat，更新 config import，保留全部 SSE/工具格式化/竞态保护/abort/权限审批代码

## 13. 可插拔渲染器（modes/renderer.py）

- [x] 13.1 定义 BaseRenderer ABC: __init__(send_fn, bus, config), 抽象方法 on_response_start/chunk/end/error, 构造时自动订阅 EventBus
- [x] 13.2 定义 RendererConfig dataclass: push_interval(3.0s), push_min_chars(2000), max_message_chars(3000), renderer_type("text")
- [x] 13.3 实现 TextRenderer: buffer 累积 → 时间/字符节流 → 分段发送 → 段落边界切分（复用已验证框架 _split_text 逻辑）
- [x] 13.4 实现多通道降级: 非 main channel 的 chunk 合并到主输出
- [x] 13.5 实现文本兜底: 中间发送失败时在 ResponseEnd 时发送完整文本

## 14. WeixinBot 主类（bot.py）

- [x] 14.1 创建 WeixinBot 类: 组装 WeixinClient + CommandRouter + HandlerRegistry + ModeManager + WeixinMonitor
- [x] 14.2 实现 _dispatch(): 白名单检查 → CommandRouter → ModeManager → HandlerRegistry（对齐已验证框架分发管道）
- [x] 14.3 实现 run() 阻塞启动: 自动检查登录 → 启动 monitor → signal 处理
- [x] 14.4 实现 start()/stop()/wait() 异步生命周期
- [x] 14.5 实现 send_text/reply 等便捷方法
- [x] 14.6 注册内置 /help 指令

## 15. 应用入口（app.py）

- [x] 15.1 实现 create_bot() 工厂: 创建 WeixinBot + EventBus + Renderer + ModeManager + 注册 Hermes/OpenCode adapter
- [x] 15.2 注册模式指令: /hermes /opencode /exit /new /modes /approve /reject /abort
- [x] 15.3 注册内置指令: /ping /echo
- [x] 15.4 注册默认消息处理器

## 16. 示例代码

- [x] 16.1 创建 examples/echo_bot.py — 最简回声 bot（3 行核心代码）
- [x] 16.2 创建 examples/openai_bot.py — OpenAI Agent 对接示例（多轮对话 + Vision）

## 17. 文档

- [x] 17.1 创建 docs/architecture.md — 整体架构文档（模块关系、消息流、可插拔设计）
- [x] 17.2 创建 docs/ilink-protocol.md — 微信 ilink 协议规范（提取自调研结果）
- [x] 17.3 创建 docs/development.md — 开发指南（环境搭建、调试、新增 Agent 适配器指南）
- [x] 17.4 创建 README.md — 项目介绍 + 快速上手 + 示例

## 18. 集成验证

- [x] 18.1 端到端验证: pyproject.toml 安装 → weixinbot 入口可运行 → QR 扫码 → 消息收发 (需微信扫码，手动验证)
- [x] 18.2 验证框架层: /help /ping 指令正常工作 (需微信扫码，手动验证)
- [x] 18.3 验证 Agent 模式: /opencode 进入模式 → 消息转发 → /exit 退出 (需微信扫码，手动验证)

## 19. 单元测试

- [x] 19.1 测试 AES-128-ECB 加解密（已知向量）
- [x] 19.2 测试 CDN 上传/下载管道（mock HTTP）
- [x] 19.3 测试 QR 登录状态机（mock API 响应：wait/scaned/confirmed/expired/redirect）
- [x] 19.4 测试长轮询重试逻辑（正常超时/连续失败退避/会话过期暂停）
- [x] 19.5 测试消息去重（LRU 缓存命中/过期）
- [x] 19.6 测试 CommandRouter 指令匹配与分发
- [x] 19.7 测试 OpenCodeAdapter SSE 事件序列（正常流/乱序/abort/权限/超时）
- [x] 19.8 测试 TextRenderer 节流与分段发送
