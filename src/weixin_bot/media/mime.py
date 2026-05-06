"""文件头魔数 MIME 类型检测"""

from __future__ import annotations

# 常见文件头魔数 → MIME 类型 + 扩展名
_SIGNATURES: list[tuple[bytes, str, str]] = [
    # 图片
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"GIF87a", "image/gif", ".gif"),
    (b"GIF89a", "image/gif", ".gif"),
    (b"RIFF", "image/webp", ".webp"),  # RIFF + WEBP
    (b"BM", "image/bmp", ".bmp"),
    # 音频
    (b"RIFF", "audio/wav", ".wav"),  # RIFF + WAVE
    (b"\x02#!SILK", "audio/silk", ".silk"),
    (b"#!AMR", "audio/amr", ".amr"),
    (b"OggS", "audio/ogg", ".ogg"),
    (b"\xff\xfb", "audio/mpeg", ".mp3"),
    (b"\xff\xf3", "audio/mpeg", ".mp3"),
    (b"ID3", "audio/mpeg", ".mp3"),
    # 视频
    (b"\x00\x00\x00", "video/mp4", ".mp4"),  # ftyp box
    # 文档
    (b"%PDF", "application/pdf", ".pdf"),
    (b"PK\x03\x04", "application/zip", ".zip"),
]


def detect_mime(data: bytes) -> tuple[str, str]:
    """通过文件头魔数检测 MIME 类型

    Args:
        data: 文件数据（至少前 16 字节）

    Returns:
        (mime_type, extension) 如 ("image/png", ".png")
        未识别时返回 ("application/octet-stream", ".bin")
    """
    if not data or len(data) < 4:
        return "application/octet-stream", ".bin"

    # RIFF 容器需要额外检查子类型
    if data[:4] == b"RIFF" and len(data) >= 12:
        if data[8:12] == b"WEBP":
            return "image/webp", ".webp"
        if data[8:12] == b"WAVE":
            return "audio/wav", ".wav"

    # MP4/MOV: ftyp box
    if len(data) >= 8 and data[4:8] == b"ftyp":
        return "video/mp4", ".mp4"

    # SILK 格式
    if data[:1] == b"\x02" and data[1:7] == b"#!SILK":
        return "audio/silk", ".silk"
    # 有些 SILK 没有前导字节
    if data[:6] == b"#!SILK":
        return "audio/silk", ".silk"

    for signature, mime, ext in _SIGNATURES:
        if data[: len(signature)] == signature:
            return mime, ext

    return "application/octet-stream", ".bin"
