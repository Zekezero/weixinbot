"""消息处理管道

入站消息解析、出站消息构建、Markdown→纯文本转换、context_token 管理。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from weixin_bot.util.random import generate_client_id

logger = logging.getLogger("weixin_bot.messaging")


# ── Markdown → 纯文本 ──────────────────────────────


def markdown_to_plaintext(text: str) -> str:
    """将 Markdown 格式文本转换为纯文本

    规则:
    - 去除代码围栏 (```...```)，保留代码内容
    - 去除图片语法 ![alt](url)
    - 去除链接格式 [text](url) → text
    - 去除表格分隔行
    - 去除行内格式 (bold **, italic *, strikethrough ~~, inline code `)
    """
    if not text:
        return text

    lines: list[str] = []
    in_code_block = False

    for line in text.split("\n"):
        # 代码围栏
        if line.strip().startswith("```"):
            in_code_block = not in_code_block
            continue

        if in_code_block:
            lines.append(line)
            continue

        # 表格分隔行 (|---|---|)
        if re.match(r"^\s*\|[\s\-:|]+\|\s*$", line):
            continue

        # 图片语法
        line = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", line)

        # 链接格式 [text](url) → text
        line = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", line)

        # 行内格式
        line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)  # bold
        line = re.sub(r"__(.+?)__", r"\1", line)  # bold alt
        line = re.sub(r"\*(.+?)\*", r"\1", line)  # italic
        line = re.sub(r"_(.+?)_", r"\1", line)  # italic alt
        line = re.sub(r"~~(.+?)~~", r"\1", line)  # strikethrough
        line = re.sub(r"`([^`]+)`", r"\1", line)  # inline code

        lines.append(line)

    return "\n".join(lines)


# ── 出站消息构建 ──────────────────────────────────


def build_text_message(
    to_user_id: str,
    text: str,
    context_token: str = "",
) -> dict[str, Any]:
    """构建文本消息（出站）"""
    # Markdown → 纯文本
    plain_text = markdown_to_plaintext(text)

    return {
        "from_user_id": "",
        "to_user_id": to_user_id,
        "client_id": generate_client_id(),
        "message_type": 2,  # BOT
        "message_state": 2,  # FINISH
        "item_list": [
            {
                "type": 1,  # TEXT
                "text_item": {"text": plain_text},
            }
        ],
        "context_token": context_token,
    }


def build_image_message(
    to_user_id: str,
    encrypt_query_param: str,
    aes_key_b64: str,
    ciphertext_size: int,
    context_token: str = "",
) -> dict[str, Any]:
    """构建图片消息（出站）"""
    return {
        "from_user_id": "",
        "to_user_id": to_user_id,
        "client_id": generate_client_id(),
        "message_type": 2,
        "message_state": 2,
        "item_list": [
            {
                "type": 2,  # IMAGE
                "image_item": {
                    "media": {
                        "encrypt_query_param": encrypt_query_param,
                        "aes_key": aes_key_b64,
                        "encrypt_type": 1,
                    },
                    "mid_size": ciphertext_size,
                },
            }
        ],
        "context_token": context_token,
    }


def build_file_message(
    to_user_id: str,
    encrypt_query_param: str,
    aes_key_b64: str,
    file_name: str,
    plaintext_size: int,
    context_token: str = "",
) -> dict[str, Any]:
    """构建文件消息（出站）"""
    return {
        "from_user_id": "",
        "to_user_id": to_user_id,
        "client_id": generate_client_id(),
        "message_type": 2,
        "message_state": 2,
        "item_list": [
            {
                "type": 4,  # FILE
                "file_item": {
                    "media": {
                        "encrypt_query_param": encrypt_query_param,
                        "aes_key": aes_key_b64,
                        "encrypt_type": 1,
                    },
                    "file_name": file_name,
                    "len": str(plaintext_size),
                },
            }
        ],
        "context_token": context_token,
    }


def build_video_message(
    to_user_id: str,
    encrypt_query_param: str,
    aes_key_b64: str,
    ciphertext_size: int,
    context_token: str = "",
) -> dict[str, Any]:
    """构建视频消息（出站）"""
    return {
        "from_user_id": "",
        "to_user_id": to_user_id,
        "client_id": generate_client_id(),
        "message_type": 2,
        "message_state": 2,
        "item_list": [
            {
                "type": 5,  # VIDEO
                "video_item": {
                    "media": {
                        "encrypt_query_param": encrypt_query_param,
                        "aes_key": aes_key_b64,
                        "encrypt_type": 1,
                    },
                    "video_size": ciphertext_size,
                },
            }
        ],
        "context_token": context_token,
    }


# ── 入站消息解析 ──────────────────────────────────


def extract_text(msg: dict[str, Any]) -> str:
    """从 WeixinMessage 提取文本内容"""
    item_list = msg.get("item_list") or []
    for item in item_list:
        item_type = item.get("type", 0)
        if item_type == 1:  # TEXT
            text_item = item.get("text_item") or {}
            return text_item.get("text", "")
        if item_type == 3:  # VOICE → transcription
            voice_item = item.get("voice_item") or {}
            transcription = voice_item.get("text", "")
            if transcription:
                return transcription

    # 引用消息中的文本
    for item in item_list:
        ref = item.get("ref_msg")
        if ref and ref.get("text"):
            return ref["text"]

    return ""


def extract_media_items(msg: dict[str, Any]) -> list[dict[str, Any]]:
    """提取消息中的媒体项"""
    result: list[dict[str, Any]] = []
    item_list = msg.get("item_list") or []

    for item in item_list:
        item_type = item.get("type", 0)
        if item_type == 2 and item.get("image_item"):
            result.append({"type": "image", "item": item["image_item"]})
        elif item_type == 3 and item.get("voice_item"):
            result.append({"type": "voice", "item": item["voice_item"]})
        elif item_type == 4 and item.get("file_item"):
            result.append({"type": "file", "item": item["file_item"]})
        elif item_type == 5 and item.get("video_item"):
            result.append({"type": "video", "item": item["video_item"]})

        # 引用消息中的媒体
        ref = item.get("ref_msg")
        if ref:
            if ref.get("image_item"):
                result.append({"type": "image", "item": ref["image_item"]})
            if ref.get("voice_item"):
                result.append({"type": "voice", "item": ref["voice_item"]})
            if ref.get("file_item"):
                result.append({"type": "file", "item": ref["file_item"]})
            if ref.get("video_item"):
                result.append({"type": "video", "item": ref["video_item"]})

    return result
