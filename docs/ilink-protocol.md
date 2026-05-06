# 微信 ilink 协议参考

## 基础信息

ilink 是微信提供的 Bot 接入协议，基于 HTTPS 长轮询实现实时消息推送。

- **基础 URL**: `https://ilinkai.weixin.qq.com`
- **CDN URL**: `https://novac2c.cdn.weixin.qq.com/c2c`
- **认证方式**: QR 码扫描 → bot_token（可能过期，errcode=-14 需重新登录）
- **消息接收**: 长轮询（无需公网 IP）

## API 端点

| 端点 | 方法 | 路径 | 超时 | 说明 |
|------|------|------|------|------|
| getupdates | POST | `/ilink/bot/getupdates` | 服务端 35s 长轮询，客户端超时 45s | 接收消息 |
| sendmessage | POST | `/ilink/bot/sendmessage` | 15s | 发送消息 |
| getuploadurl | POST | `/ilink/bot/getuploadurl` | 15s | 获取 CDN 预签名上传地址 |
| getconfig | POST | `/ilink/bot/getconfig` | 10s | 获取配置（typing_ticket） |
| sendtyping | POST | `/ilink/bot/sendtyping` | 10s | 发送输入状态指示器 |
| get_bot_qrcode | GET | `/ilink/bot/get_bot_qrcode` | 5s | 获取登录二维码 |
| get_qrcode_status | GET | `/ilink/bot/get_qrcode_status` | 服务端 35s 长轮询，客户端超时 45s | 查询扫码状态 |

## 标准请求头

所有请求必须携带以下头部：

| 头部 | 说明 | 示例 |
|------|------|------|
| Content-Type | 内容类型 | `application/json` |
| AuthorizationType | 认证类型标识 | `ilink_bot_token` |
| X-WECHAT-UIN | 微信 UIN（base64 随机数即可） | `MTIzNDU=` |
| Authorization | Bearer token | `Bearer {bot_token}` |

## QR 码登录

### 获取二维码

```
GET /ilink/bot/get_bot_qrcode?bot_type=3
```

响应：
```json
{
  "qrcode": "轮询状态用的 token（不是 QR 码内容）",
  "qrcode_img_content": "https://xxx（实际要编码为 QR 码让微信扫描的 URL）"
}
```

**关键**：QR 码编码的内容是 `qrcode_img_content`（URL），不是 `qrcode`（token）。

### 轮询扫码状态

```
GET /ilink/bot/get_qrcode_status?qrcode={qrcode}
```

响应 status 字段：

| 状态 | 说明 | 处理方式 |
|------|------|----------|
| `wait` | 等待扫码 | 继续轮询 |
| `scaned` | 已扫码，等待确认 | 继续轮询 |
| `confirmed` | 已确认登录 | 获取 bot_token + ilink_bot_id |
| `expired` | 二维码过期 | 重新获取二维码（最多 3 次） |
| `scaned_but_redirect` | IDC 重定向 | 切换轮询 base URL 为 `https://{redirect_host}` |

登录成功响应：
```json
{
  "status": "confirmed",
  "bot_token": "持久化保存的认证 token",
  "ilink_bot_id": "bot 账号 ID",
  "baseurl": "该账号的 API 基础 URL（可能与默认不同）",
  "ilink_user_id": "扫码用户 ID"
}
```

## 消息收发

### getupdates（消息接收）

长轮询接口，保持连接最多 35 秒等待服务器推送消息。

请求体：
```json
{
  "get_updates_buf": "上次返回的游标（base64 字符串，首次为空）",
  "base_info": {
    "channel_version": "0.1.0"
  }
}
```

响应体：
```json
{
  "ret": 0,
  "errcode": 0,
  "errmsg": "",
  "msgs": [WeixinMessage, ...],
  "get_updates_buf": "新的游标（必须持久化保存）",
  "longpolling_timeout_ms": 35000
}
```

### sendmessage（消息发送）

请求体：
```json
{
  "msg": {WeixinMessage 结构},
  "base_info": {"channel_version": "0.1.0"}
}
```

## 消息结构（WeixinMessage）

```json
{
  "seq": 1,
  "message_id": 12345678,
  "from_user_id": "发送者 ilink_user_id",
  "to_user_id": "接收者 ilink_bot_id",
  "client_id": "客户端生成的唯一 ID",
  "create_time_ms": 1700000000000,
  "session_id": "",
  "message_type": 1,
  "message_state": 2,
  "context_token": "用于回复的关联 token（必须回传）",
  "item_list": [MessageItem, ...]
}
```

### message_type

| 值 | 含义 |
|----|------|
| 1 | 用户消息 (USER) |
| 2 | 机器人消息 (BOT) |

### message_state

| 值 | 含义 |
|----|------|
| 0 | NEW |
| 1 | GENERATING（流式中） |
| 2 | FINISH（完成） |

### MessageItem

```json
{
  "type": 1,
  "create_time_ms": 0,
  "msg_id": "",
  "text_item": {"text": "消息内容"},
  "image_item": null,
  "voice_item": null,
  "file_item": null,
  "video_item": null,
  "ref_msg": null
}
```

### MessageItem type 类型

| type | 类型 | item 字段 |
|------|------|-----------|
| 1 | 文本 | `text_item.text` |
| 2 | 图片 | `image_item.media` (CDNMedia) |
| 3 | 语音 | `voice_item.media` (CDNMedia) + `voice_item.text`（转写） |
| 4 | 文件 | `file_item.media` (CDNMedia) + `file_item.file_name` |
| 5 | 视频 | `video_item.media` (CDNMedia) |

### CDNMedia 结构

```json
{
  "encrypt_query_param": "CDN 下载参数（URL query）",
  "aes_key": "AES 密钥（base64 或 hex 编码）",
  "encrypt_type": 0,
  "full_url": "完整下载 URL（如果有则优先使用）"
}
```

### context_token

- 每条入站消息携带 `context_token`
- 发送回复时**必须**在 `msg.context_token` 字段回传对应用户的 token
- 按 `accountId:userId` 缓存（进程内无 TTL，收到入站消息时更新）
- 发送时尽量回传 context_token，若为空可能导致服务端拒绝（框架不强制校验）

## CDN 加密机制

### 加密参数

- **算法**: AES-128-ECB
- **填充**: PKCS7
- **密钥长度**: 128 位（16 字节）

### 密钥格式

服务器返回的 `aes_key` 可能有三种格式：

| 格式 | 识别方式 | 解析方法 |
|------|----------|----------|
| 直接 Hex | 32 字符全 hex | `bytes.fromhex(key)` |
| Base64(raw 16 bytes) | base64 解码后 16 字节 | `base64.b64decode(key)` |
| Base64(hex string) | base64 解码后为 32 字符 hex | `bytes.fromhex(base64.b64decode(key).decode())` |

### CDN 上传流程

```
1. 读取本地文件 → 计算 MD5
2. 生成随机 16 字节 AES 密钥 + 随机 filekey
3. AES-128-ECB 加密文件（PKCS7 填充）
4. POST /ilink/bot/getuploadurl 获取预签名 URL
5. POST 密文到 CDN upload URL
6. 从响应头 x-encrypted-param 获取下载参数
```

getuploadurl 请求：
```json
{
  "filekey": "随机 32 字符 hex",
  "media_type": 1,
  "to_user_id": "目标用户 ID",
  "rawsize": 原文大小,
  "rawfilemd5": "原文 MD5 hex",
  "filesize": 密文大小,
  "no_need_thumb": true,
  "aeskey": "AES 密钥 hex 编码",
  "base_info": {"channel_version": "0.1.0"}
}
```

media_type 值：

| 值 | 类型 |
|----|------|
| 1 | 图片 |
| 2 | 视频 |
| 3 | 文件 |
| 4 | 语音 |

### CDN 下载流程

```
1. 从 CDNMedia 获取 encrypt_query_param（或 full_url）
2. 构建下载 URL: {CDN_BASE}/download?encrypted_query_param={eqp}
3. GET 下载密文
4. 解析 AES 密钥（支持三种格式）
5. AES-128-ECB 解密 + 去 PKCS7 填充
```

## Typing 指示器

### 获取 typing_ticket

```json
// POST /ilink/bot/getconfig
{
  "ilink_user_id": "目标用户 ID",
  "context_token": "用户的 context_token（可选）",
  "base_info": {"channel_version": "0.1.0"}
}

// 响应
{
  "ret": 0,
  "typing_ticket": "base64 编码的 ticket"
}
```

typing_ticket 缓存策略：per-user，TTL 24 小时。

### 发送输入状态

```json
// POST /ilink/bot/sendtyping
{
  "ilink_user_id": "目标用户 ID",
  "typing_ticket": "从 getconfig 获取的 ticket",
  "status": 1,
  "base_info": {"channel_version": "0.1.0"}
}
```

| status | 含义 |
|--------|------|
| 1 | 开始输入（显示"正在输入..."） |
| 2 | 结束输入（隐藏状态） |

### 最佳实践

- 收到消息后立即发送 `status: 1`
- 每 10 秒刷新一次 `status: 1`（防止超时消失）
- 发送最终回复前发送 `status: 2`

## 长轮询生命周期

### 重试策略

| 场景 | 行为 |
|------|------|
| 正常超时（35s 无消息） | 立即重新发起请求 |
| 客户端网络超时 | 等待 2s 后重试 |
| 服务端错误（ret != 0） | 等待 2s 后重试 |
| 连续 3 次失败 | 等待 30s（退避） |
| 会话过期（errcode=-14） | 暂停 1 小时，提示重新登录 |

### get_updates_buf 持久化

- 每次成功响应后保存新的 `get_updates_buf` 到磁盘
- 程序重启后从磁盘加载，从上次位置继续接收
- 丢失 `get_updates_buf` 可能导致消息重复或丢失

### 消息去重

- 基于 `message_id` 做 LRU 缓存去重
- 缓存容量 10000 条，TTL 30 分钟
- 命中缓存的消息静默跳过

## 错误码参考

| 错误码 | 说明 | 处理建议 |
|--------|------|----------|
| 0 | 成功 | 正常处理 |
| -1 | 长轮询超时（正常） | 立即重试 |
| -7 | 频率限制 | 降低请求频率 |
| -14 | 会话过期 | 暂停 1 小时后重新登录 |
| -100 | 未授权 | 检查 bot_token |
| -101 | 二维码过期 | 重新获取二维码 |

## 音频格式

微信语音消息使用 SILK 编码格式：
- 编码: SILK V3
- 采样率: 24000 Hz
- 文件头: `\x02#!SILK` 或 `#!SILK`

转码为 WAV（PCM 16-bit LE, mono, 24000Hz）需要 silk 解码库（可选依赖）。
