"""统一媒体下载入口

根据 MessageItemType 路由到对应处理逻辑。
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

from weixin_bot.cdn.download import download_and_decrypt
from weixin_bot.client import WeixinClient
from weixin_bot.errors import MediaError
from weixin_bot.media.mime import detect_mime
from weixin_bot.media.silk_transcode import silk_to_wav

logger = logging.getLogger("weixin_bot.media.download")

# 临时文件目录
MEDIA_TEMP_DIR = os.path.join(tempfile.gettempdir(), "weixinbot", "media")


def _ensure_media_dir() -> Path:
    path = Path(MEDIA_TEMP_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _get_aes_key(item: dict[str, Any], media_key: str = "media") -> str:
    """从消息项中提取 AES 密钥

    优先使用外层 aeskey，其次 media.aes_key
    """
    # 外层直接的 aeskey（ImageItem 特有）
    outer_key = item.get("aeskey", "")
    if outer_key:
        return outer_key

    media = item.get(media_key)
    if media and isinstance(media, dict):
        return media.get("aes_key", "")

    return ""


def _get_cdn_info(item: dict[str, Any], media_key: str = "media") -> tuple[str, str]:
    """提取 CDN 下载信息: (encrypt_query_param, full_url)"""
    media = item.get(media_key)
    if not media or not isinstance(media, dict):
        return "", ""
    return media.get("encrypt_query_param", ""), media.get("full_url", "")


async def download_image(
    client: WeixinClient,
    image_item: dict[str, Any],
    msg_id: str = "",
) -> str | None:
    """下载图片并保存到临时文件"""
    aes_key = _get_aes_key(image_item)
    eqp, full_url = _get_cdn_info(image_item)

    if not aes_key or (not eqp and not full_url):
        logger.warning("图片消息缺少 AES 密钥或下载参数")
        return None

    data = await download_and_decrypt(client, eqp, aes_key, full_url=full_url)
    _, ext = detect_mime(data)
    return _save_to_temp(data, f"img_{msg_id}", ext)


async def download_voice(
    client: WeixinClient,
    voice_item: dict[str, Any],
    msg_id: str = "",
) -> str | None:
    """下载语音并尝试 SILK→WAV 转码"""
    aes_key = _get_aes_key(voice_item)
    eqp, full_url = _get_cdn_info(voice_item)

    if not aes_key or (not eqp and not full_url):
        logger.warning("语音消息缺少 AES 密钥或下载参数")
        return None

    data = await download_and_decrypt(client, eqp, aes_key, full_url=full_url)

    # 尝试 SILK→WAV 转码
    sample_rate = voice_item.get("sample_rate", 24000) or 24000
    wav_data = silk_to_wav(data, sample_rate)
    if wav_data:
        return _save_to_temp(wav_data, f"voice_{msg_id}", ".wav")

    # 保留原始 SILK
    return _save_to_temp(data, f"voice_{msg_id}", ".silk")


async def download_file(
    client: WeixinClient,
    file_item: dict[str, Any],
    msg_id: str = "",
) -> str | None:
    """下载文件附件"""
    aes_key = _get_aes_key(file_item)
    eqp, full_url = _get_cdn_info(file_item)

    if not aes_key or (not eqp and not full_url):
        logger.warning("文件消息缺少 AES 密钥或下载参数")
        return None

    data = await download_and_decrypt(client, eqp, aes_key, full_url=full_url)
    file_name = file_item.get("file_name", "")
    ext = Path(file_name).suffix if file_name else ".bin"
    prefix = file_name or f"file_{msg_id}"
    return _save_to_temp(data, prefix, ext if ext else ".bin")


async def download_video(
    client: WeixinClient,
    video_item: dict[str, Any],
    msg_id: str = "",
) -> str | None:
    """下载视频"""
    aes_key = _get_aes_key(video_item)
    eqp, full_url = _get_cdn_info(video_item)

    if not aes_key or (not eqp and not full_url):
        logger.warning("视频消息缺少 AES 密钥或下载参数")
        return None

    data = await download_and_decrypt(client, eqp, aes_key, full_url=full_url)
    _, ext = detect_mime(data)
    return _save_to_temp(data, f"video_{msg_id}", ext)


def _save_to_temp(data: bytes, prefix: str, ext: str) -> str:
    """保存数据到临时文件"""
    media_dir = _ensure_media_dir()
    # 用内容 hash 避免重复文件
    import hashlib

    content_hash = hashlib.md5(data).hexdigest()[:8]
    safe_prefix = "".join(c for c in prefix if c.isalnum() or c in "-_.")[:50]
    filename = f"{safe_prefix}_{content_hash}{ext}"
    filepath = media_dir / filename
    filepath.write_bytes(data)
    logger.debug("媒体文件已保存: %s (%d bytes)", filepath, len(data))
    return str(filepath)
