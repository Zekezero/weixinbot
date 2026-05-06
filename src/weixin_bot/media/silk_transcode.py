"""SILK → WAV 音频转码（可选依赖）"""

from __future__ import annotations

import logging
import struct

logger = logging.getLogger("weixin_bot.media.silk_transcode")

DEFAULT_SAMPLE_RATE = 24000


def silk_to_wav(silk_data: bytes, sample_rate: int = DEFAULT_SAMPLE_RATE) -> bytes | None:
    """将 SILK 音频转码为 WAV

    Args:
        silk_data: SILK 格式音频数据
        sample_rate: 采样率（Hz），默认 24000

    Returns:
        WAV 格式数据，或 None（如果 silk 解码库不可用）
    """
    try:
        import pilk  # type: ignore[import-untyped]
    except ImportError:
        logger.debug("pilk 库不可用，跳过 SILK 转码（pip install pilk）")
        return None

    try:
        pcm_data = pilk.decode(silk_data, sample_rate)
    except Exception as exc:
        logger.warning("SILK 解码失败: %s", exc)
        return None

    # 构建 WAV 容器
    return _build_wav(pcm_data, sample_rate)


def _build_wav(pcm_data: bytes, sample_rate: int) -> bytes:
    """将 PCM 16-bit LE mono 数据包装为 WAV 文件"""
    channels = 1
    bits_per_sample = 16
    byte_rate = sample_rate * channels * bits_per_sample // 8
    block_align = channels * bits_per_sample // 8
    data_size = len(pcm_data)
    file_size = 36 + data_size  # RIFF header(44) - 8

    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        file_size,
        b"WAVE",
        b"fmt ",
        16,  # subchunk1 size
        1,  # audio format (PCM)
        channels,
        sample_rate,
        byte_rate,
        block_align,
        bits_per_sample,
        b"data",
        data_size,
    )

    return header + pcm_data
