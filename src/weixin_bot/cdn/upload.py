"""CDN 上传管道

读取文件 → MD5 → 生成 AES 密钥 → 加密 → getUploadUrl → POST 密文 → 解析 x-encrypted-param
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from weixin_bot.api import WeixinAPI
from weixin_bot.cdn import (
    aes_ecb_encrypt,
    encrypted_size,
    generate_aes_key,
    key_to_base64,
    key_to_hex,
)
from weixin_bot.client import WeixinClient
from weixin_bot.errors import CdnError
from weixin_bot.util.random import generate_filekey

logger = logging.getLogger("weixin_bot.cdn.upload")

MAX_UPLOAD_RETRIES = 3


async def upload_media(
    client: WeixinClient,
    file_path: str | Path,
    media_type: int,
    to_user_id: str,
) -> dict[str, str]:
    """上传媒体文件到微信 CDN

    Args:
        client: HTTP 客户端
        file_path: 本地文件路径
        media_type: UploadMediaType 枚举值 (1=IMAGE, 2=VIDEO, 3=FILE, 4=VOICE)
        to_user_id: 目标用户 ID

    Returns:
        dict with keys: encrypt_query_param, aes_key_b64, ciphertext_size
    """
    path = Path(file_path)
    if not path.exists():
        raise CdnError(f"文件不存在: {path}")

    plaintext = path.read_bytes()
    plaintext_md5 = hashlib.md5(plaintext).hexdigest()
    plaintext_size = len(plaintext)

    # 生成 AES 密钥并加密
    aes_key = generate_aes_key()
    ciphertext = aes_ecb_encrypt(plaintext, aes_key)
    ciphertext_size = len(ciphertext)
    filekey = generate_filekey()

    # 获取预签名上传 URL
    api = WeixinAPI(client)
    resp = await api.get_upload_url(
        filekey=filekey,
        media_type=media_type,
        to_user_id=to_user_id,
        rawsize=plaintext_size,
        rawfilemd5=plaintext_md5,
        filesize=ciphertext_size,
        aeskey=key_to_hex(aes_key),
    )

    upload_url = resp.get("upload_full_url", "")
    if not upload_url:
        upload_param = resp.get("upload_param", "")
        if not upload_param:
            raise CdnError(f"getUploadUrl 返回无效: {resp}")
        from urllib.parse import quote

        upload_url = (
            f"https://novac2c.cdn.weixin.qq.com/c2c/upload"
            f"?encrypted_query_param={quote(upload_param)}"
            f"&filekey={quote(filekey)}"
        )

    # 上传密文（带重试）
    encrypt_query_param = ""
    last_error: Exception | None = None

    for attempt in range(1, MAX_UPLOAD_RETRIES + 1):
        try:
            upload_resp = await client.post_binary(upload_url, ciphertext, timeout=60)
            encrypt_query_param = upload_resp.headers.get("x-encrypted-param", "")
            if not encrypt_query_param:
                error_msg = upload_resp.headers.get("x-error-message", "")
                raise CdnError(f"CDN 上传未返回 x-encrypted-param: {error_msg}")
            break
        except Exception as exc:
            last_error = exc
            if attempt < MAX_UPLOAD_RETRIES:
                logger.warning("CDN 上传失败 (第 %d 次): %s", attempt, exc)
            else:
                raise CdnError(f"CDN 上传失败 ({MAX_UPLOAD_RETRIES} 次重试后): {last_error}")

    return {
        "encrypt_query_param": encrypt_query_param,
        "aes_key_b64": key_to_base64(aes_key),
        "ciphertext_size": str(ciphertext_size),
    }
