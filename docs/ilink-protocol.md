# ilink 协议参考文档

## 基础信息

ilink 是微信提供的 Bot 接入协议，基于 HTTPS 长轮询实现实时消息推送。

**基础 URL**：`https://ilinkai.weixin.qq.com`

**CDN URL**：`https://novac2c.cdn.weixin.qq.com/c2c`

所有 API 请求均使用 JSON 格式，需要携带特定的认证头部。

## API 端点

| 端点 | 方法 | 路径 | 超时 | 说明 |
|------|------|------|------|------|
| getupdates | POST | `/cgi-bin/getupdates` | 35s | 长轮询获取消息 |
| sendmessage | POST | `/cgi-bin/sendmessage` | 15s | 发送消息 |
| getuploadurl | POST | `/cgi-bin/getuploadurl` | 30s | 获取上传 URL |
| getconfig | POST | `/cgi-bin/getconfig` | 30s | 获取配置信息 |
| sendtyping | POST | `/cgi-bin/sendtyping` | 10s | 发送输入状态 |
| get_bot_qrcode | GET | `/cgi-bin/get_bot_qrcode` | 30s | 获取登录二维码 |
| get_qrcode_status | GET | `/cgi-bin/get_qrcode_status` | 35s | 查询二维码状态 |

### getupdates（消息接收）

核心长轮询接口，保持连接 35 秒等待服务器推送消息。

请求体：
```json
{
  "sync_buf": "base64_encoded_buffer",
  "timeout": 35000
}
```

响应体：
```json
{
  "errcode": 0,
  "errmsg": "ok",
  "data": {
    "sync_buf": "new_base64_buffer",
    "item_list": [
      {
        "type": 1,
        "content": "消息内容",
        "from_user": "wxid_xxx",
        "to_user": "wxid_xxx",
        "msg_id": "1234567890",
        "timestamp": 1234567890
      }
    ]
  }
}
```

### sendmessage（消息发送）

发送文本或媒体消息到指定用户。

请求体：
```json
{
  "to_user": "wxid_xxx",
  "msg_type": 1,
  "content": "消息内容",
  "media_id": ""
}
```

## 标准请求头部

所有请求必须携带以下头部：

| 头部 | 说明 | 示例 |
|------|------|------|
| Content-Type | 内容类型 | `application/json` |
| AuthorizationType | 认证类型 | `2` |
| X-WECHAT-UIN | 微信 UIN | `1234567890` |
| Authorization | 认证令牌 | `Bearer xxxxxx` |

Authorization 的计算方式：
```python
auth_token = base64(f"{uin}:{token}").decode()
headers["Authorization"] = f"Bearer {auth_token}"
```

## 消息结构

ilink 协议的消息封装在 `WeixinMessage` 对象中，包含 `item_list` 数组，每个元素是 `MessageItem`。

### MessageItem 类型

| type 值 | 类型 | 说明 |
|---------|------|------|
| 1 | 文本消息 | 纯文本内容 |
| 2 | 图片消息 | 包含图片 URL |
| 3 | 语音消息 | 包含语音文件 URL |
| 4 | 视频消息 | 包含视频文件 URL |
| 5 | 文件消息 | 包含文件下载信息 |

### 文本消息示例

```json
{
  "type": 1,
  "content": "你好，机器人",
  "from_user": "wxid_xxxxxxxx",
  "to_user": "wxid_yyyyyyyy",
  "msg_id": "1234567890123456789",
  "timestamp": 1700000000,
  "chat_type": 1
}
```

### 图片消息示例

```json
{
  "type": 2,
  "content": "",
  "media_url": "https://novac2c.cdn.weixin.qq.com/c2c/xxx",
  "aes_key": "base64_encoded_key",
  "file_size": 12345,
  "from_user": "wxid_xxxxxxxx",
  "to_user": "wxid_yyyyyyyy",
  "msg_id": "1234567890123456789",
  "timestamp": 1700000000
}
```

## CDN 加密机制

CDN 媒体文件（图片、语音、视频）采用 AES-128-ECB 加密，需要解密后才能使用。

### 加密参数

- **算法**：AES-128-ECB
- **填充**：PKCS7
- **密钥长度**：128 位（16 字节）

### 密钥格式

服务器返回的 `aes_key` 可能有三种格式：

1. **Base64 原始**：直接是 16 字节的 base64 编码
2. **Base64 Hex**：base64 编码的 hex 字符串
3. **直接 Hex**：32 字符的 hex 字符串

解密示例（Python）：
```python
from Crypto.Cipher import AES
import base64

def decrypt_media(encrypted_data: bytes, aes_key: str) -> bytes:
    # 尝试多种密钥格式
    key = decode_aes_key(aes_key)
    cipher = AES.new(key, AES.MODE_ECB)
    decrypted = cipher.decrypt(encrypted_data)
    # 去除 PKCS7 填充
    padding_len = decrypted[-1]
    return decrypted[:-padding_len]
```

## 二维码登录状态机

二维码登录采用轮询机制，状态转换如下：

```
┌─────────┐    扫码     ┌─────────┐    确认     ┌─────────┐
│  wait   │ ─────────▶ │ scanned │ ─────────▶ │confirmed│
│ (等待)  │            │ (已扫码) │            │ (已确认) │
└────┬────┘            └────┬────┘            └─────────┘
     │                      │
     │ 超时                 │ 超时/取消
     ▼                      ▼
┌─────────┐              ┌─────────┐
│ expired │              │redirect │
│ (过期)  │              │(需重定向)│
└─────────┘              └─────────┘
```

### 状态说明

| 状态 | 说明 | 处理方式 |
|------|------|----------|
| wait | 等待扫码 | 继续轮询 |
| scanned | 已扫码，等待确认 | 继续轮询 |
| confirmed | 已确认登录 | 获取 token，开始运行 |
| expired | 二维码过期 | 重新获取二维码 |
| scaned_but_redirect | 需要重定向 | 根据返回的 URL 重新请求 |

## 长轮询生命周期

长轮询是消息接收的核心机制，需要正确处理各种边界情况。

### 正常流程

```
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐
│  Start  │────▶│ Request │────▶│  Wait   │────▶│ Response│
└─────────┘     └─────────┘     │  35s    │     └────┬────┘
                                └─────────┘          │
                                                     │
              ┌──────────────────────────────────────┘
              │
              ▼
┌─────────┐     ┌─────────┐     ┌─────────┐
│ Process │────▶│  Save   │────▶│  Loop   │
│ Messages│     │sync_buf │     │  Back   │
└─────────┘     └─────────┘     └─────────┘
```

### 重试策略

| 场景 | 重试间隔 | 说明 |
|------|----------|------|
| 网络超时 | 2s | 连接超时，立即重试 |
| 服务器错误 | 30s | 5xx 错误，稍后再试 |
| 会话过期 | 1h | errcode -14，暂停运行 |

### sync_buf 持久化

`sync_buf` 是长轮询的状态标识，必须持久化存储：
- 正常响应后保存新的 `sync_buf`
- 程序重启后读取上次保存的 `sync_buf`
- 丢失 `sync_buf` 可能导致消息丢失或重复

### 会话过期处理

当返回 `errcode: -14` 时，表示会话已过期：
1. 立即停止长轮询
2. 清除本地保存的 token
3. 进入暂停状态，等待 1 小时后重试
4. 或提示用户重新登录

## 输入状态指示器

微信支持显示"对方正在输入..."状态，通过以下流程实现：

### 获取 typing_ticket

首先调用 `getconfig` 获取 `typing_ticket`：

```json
// 请求
{
  "uin": "1234567890"
}

// 响应
{
  "errcode": 0,
  "data": {
    "typing_ticket": "base64_encoded_ticket"
  }
}
```

### 发送输入状态

使用 `sendtyping` 接口：

```json
// 开始输入
{
  "to_user": "wxid_xxx",
  "typing_ticket": "xxx",
  "status": 1
}

// 结束输入
{
  "to_user": "wxid_xxx",
  "typing_ticket": "xxx",
  "status": 2
}
```

| status | 含义 |
|--------|------|
| 1 | 开始输入，显示"正在输入..." |
| 2 | 结束输入，隐藏状态 |

### 最佳实践

- 收到消息后立即发送 `status: 1`
- 开始处理回复时发送 `status: 1`（刷新状态）
- 发送最终回复前发送 `status: 2`
- 每次 `typing_ticket` 有效期约 30 秒

## 错误码参考

| 错误码 | 说明 | 处理建议 |
|--------|------|----------|
| 0 | 成功 | 正常处理 |
| -1 | 系统错误 | 稍后重试 |
| -2 | 参数错误 | 检查请求参数 |
| -7 | 频率限制 | 降低请求频率 |
| -14 | 会话过期 | 重新登录 |
| -100 | 未授权 | 检查 token |
| -101 | 二维码过期 | 重新获取二维码 |
