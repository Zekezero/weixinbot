# Changelog

## [0.1.0] - 2026-05-06

### Added
- 项目初始化 — 完整的 Python 异步微信机器人框架
- 微信 ilink 通信层：QR 扫码登录、长轮询 getUpdates、消息收发、Typing 指示器
- CDN 媒体处理：AES-128-ECB 加解密、上传/下载管道、SILK→WAV 语音转码
- 框架核心：WeixinBot 入口类、CommandRouter 指令系统、HandlerRegistry 事件路由
- Agent 模式系统：ModeManager + AgentAdapter + EventBus 解耦架构
- 可插拔渲染器：BaseRenderer ABC + TextRenderer（分段文本，节流控制）
- Agent 适配器：HermesAdapter (SSE)、OpenCodeAdapter (SSE + 状态机 + 竞态保护)
- 消息去重：LRU 缓存，容量 10000，TTL 30 分钟
- 会话恢复：sync buf 持久化、errcode -14 会话过期暂停 1 小时
- 连续失败退避：2s → 30s（3 次失败后）
- 文档：架构文档、ilink 协议规范、开发指南
- 示例：echo_bot、openai_bot
- 单元测试：74 个测试用例覆盖核心模块
