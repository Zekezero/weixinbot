"""CDN 下载 + 解密管道

构建下载 URL → 下载密文 → 解析 AES 密钥 → AES-128-ECB 解密
"""

from __future__ import annotations

import logging
from urllib.parse import quote

from weixin_bot.cdn import aes_ecb_decrypt, parse_aes_key
from weixin_bot.client import CDN_BASE_URL, WeixinClient
from weixin_bot.errors import CdnError

logger = logging.getLogger("weixin_bot.cdn.download")


def build_cdn_download_url(encrypt_query_param: str) -> str:
    """构建 CDN 下载 URL"""
    return f"{CDN_BASE_URL}/download?encrypted_query_param={quote(encrypt_query_param)}"


async def download_and_decrypt(
    client: WeixinClient,
    encrypt_query_param: str,
    aes_key_raw: str,
    *,
    full_url: str = "",
) -> bytes:
    """从 CDN 下载加密媒体并解密

    Args:
        client: HTTP 客户端
        encrypt_query_param: CDNMedia.encrypt_query_param
        aes_key_raw: CDNMedia.aes_key (base64 或 hex 编码)
        full_url: CDNMedia.full_url (如果有，优先使用)

    Returns:
        解密后的明文数据
    """
    # 解析 AES 密钥
    try:
        key = parse_aes_key(aes_key_raw)
    except ValueError as exc:
        raise CdnError(f"无法解析 AES 密钥: {exc}") from exc

    # 构建下载 URL
    url = full_url or build_cdn_download_url(encrypt_query_param)
    if not url:
        raise CdnError("无法构建下载 URL: encrypt_query_param 和 full_url 均为空")

    # 下载密文
    try:
        ciphertext = await client.get_binary(url, timeout=60)
    except Exception as exc:
        raise CdnError(f"CDN 下载失败: {exc}") from exc

    if not ciphertext:
        raise CdnError("CDN 下载返回空数据")

    # 解密
    try:
        return aes_ecb_decrypt(ciphertext, key)
    except Exception as exc:
        raise CdnError(f"AES 解密失败: {exc}") from exc
