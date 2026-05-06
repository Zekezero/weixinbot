## ADDED Requirements

### Requirement: AES-128-ECB Encryption
系统 SHALL 使用 AES-128-ECB + PKCS7 padding 对 CDN 媒体进行加解密。

#### Scenario: 加密上传
- **WHEN** 需要上传媒体文件
- **THEN** 系统 SHALL 生成随机 16 字节 AES 密钥，使用 AES-128-ECB 加密文件内容（PKCS7 填充），密文大小为 `ceil((plaintext_size + 1) / 16) * 16`

#### Scenario: 解密下载
- **WHEN** 收到加密媒体（CDNMedia 引用）
- **THEN** 系统 SHALL 从 CDN 下载密文，解析 AES 密钥（支持 base64(raw 16 bytes) 和 base64(hex string) 两种编码），使用 AES-128-ECB 解密并去除 PKCS7 填充

### Requirement: CDN Upload Pipeline
系统 SHALL 支持完整的 CDN 上传流程：获取预签名 URL → 加密 → 上传。

#### Scenario: 图片上传
- **WHEN** Agent 响应包含本地图片路径
- **THEN** 系统 SHALL: 1) 计算明文 MD5，2) 生成随机 AES 密钥和 filekey，3) 加密文件，4) 调用 getUploadUrl 获取上传地址，5) POST 密文到 CDN，6) 从响应头 `x-encrypted-param` 获取下载参数

#### Scenario: 上传重试
- **WHEN** CDN 上传返回 5xx 错误
- **THEN** 系统 SHALL 重试最多 3 次；4xx 错误 SHALL 立即失败

### Requirement: CDN Download Pipeline
系统 SHALL 支持从 CDN 下载加密媒体并解密到本地。

#### Scenario: 图片下载
- **WHEN** 入站消息包含 ImageItem
- **THEN** 系统 SHALL 从 CDNMedia.full_url 或构建下载 URL（`/c2c/download?encrypted_query_param=...`），下载密文并用 AES 密钥解密

#### Scenario: 语音下载
- **WHEN** 入站消息包含 VoiceItem
- **THEN** 系统 SHALL 下载解密 SILK 音频，尝试 SILK→WAV 转码（24000Hz 采样率），转码失败则保留原始 SILK

### Requirement: Media Type Support
系统 SHALL 支持图片、语音、视频、文件四种媒体类型的上传和下载。

#### Scenario: 支持的媒体类型
- **WHEN** 处理媒体消息
- **THEN** 系统 SHALL 根据 MessageItemType（IMAGE=2, VOICE=3, FILE=4, VIDEO=5）正确路由到对应的处理逻辑

#### Scenario: MIME 类型检测
- **WHEN** 下载媒体文件后
- **THEN** 系统 SHALL 通过文件头魔数检测实际 MIME 类型，用于确定文件扩展名

### Requirement: SILK Audio Transcoding
系统 SHALL 支持可选的 SILK→WAV 音频转码。

#### Scenario: 转码成功
- **WHEN** 收到 SILK 格式语音且 silk-decode 库可用
- **THEN** 系统 SHALL 转码为 WAV（PCM 16-bit LE，单声道，24000Hz）

#### Scenario: 转码不可用
- **WHEN** silk-decode 库不可用
- **THEN** 系统 SHALL 保留原始 SILK 文件，不阻断消息处理
