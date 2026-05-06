"""Hermes Agent adapter with SSE streaming."""

from __future__ import annotations

import json
import time
import uuid
from typing import TypeGuard, cast

import httpx

from weixin_bot.config import WeixinBotConfig
from weixin_bot.modes.adapter import AgentAdapter, MessageContext
from weixin_bot.modes.events import (
    EventBus,
    ResponseChunk,
    ResponseEnd,
    ResponseError,
    ResponseStart,
)

DEFAULT_FILE_PROMPT = (
    "你可以通过以下标记在回复中发送文件和图片：\n"
    "\n"
    "- [image: /path/to/image.png] — 发送图片（本地路径或HTTP URL均可）\n"
    "- [file: /path/to/file.csv] — 发送文件（自动检测类型）\n"
    "\n"
    "示例：\n"
    "[image: /tmp/chart.png]\n"
    "[image: https://example.com/screenshot.png]\n"
    "[file: /tmp/report.csv]\n"
    "[file: /tmp/data.xlsx]\n"
    "\n"
    "注意：路径必须是存在的绝对路径。支持图片(png/jpg/gif/webp/bmp)、"
    "音频(mp3/wav/amr)、视频(mp4/mov)、以及其他文件类型。"
)


class HermesAdapter(AgentAdapter):
    """Hermes Agent adapter with SSE streaming support."""

    name: str = "hermes"
    display_name: str = "Hermes Agent"

    def __init__(self, config: WeixinBotConfig, bus: EventBus) -> None:
        super().__init__(bus)
        self._bus: EventBus = bus
        self._config: WeixinBotConfig = config
        self._base_url: str = config.hermes_base_url.rstrip("/")
        self._api_key: str = config.hermes_api_key
        self._session_map: dict[str, str] = {}

    async def create_session(self) -> str:
        return str(uuid.uuid4())

    async def send(
        self,
        session_id: str,
        message: str,
        context: MessageContext,
        *,
        user_id: str,
    ) -> str:
        start_time = time.monotonic()
        url = f"{self._base_url}/v1/chat/completions"

        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        hermes_session_id = self._session_map.get(session_id)
        if hermes_session_id:
            headers["X-Hermes-Session-Id"] = hermes_session_id

        # 构建消息上下文（平台无关）
        ctx_tag = (
            f"[Context: {context.chat_type} chat, user: {context.sender_id}, "
            f"deliver: weixin:{context.chat_type}:{context.chat_id}]"
        )
        effective_message = f"{ctx_tag}\n{message}" if message else ctx_tag

        if context.image_urls:
            parts = [effective_message] if effective_message else []
            for image_url in context.image_urls:
                parts.append(f"[User sent an image. URL: {image_url}]")
            effective_message = "\n".join(parts)

        messages = [
            {"role": "system", "content": DEFAULT_FILE_PROMPT},
            {"role": "user", "content": effective_message},
        ]

        body = {
            "model": "hermes-agent",
            "messages": messages,
            "stream": True,
        }

        timeout = httpx.Timeout(timeout=None, read=300)
        full_response = ""

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                async with client.stream(
                    "POST",
                    url,
                    json=body,
                    headers=headers,
                ) as response:
                    if response.status_code != 200:
                        error_body = await response.aread()
                        error_text = error_body.decode("utf-8", errors="replace")
                        raise RuntimeError(
                            f"Hermes API error {response.status_code}: {error_text}"
                        )

                    new_session_id = cast(
                        str | None,
                        response.headers.get("X-Hermes-Session-Id"),
                    )
                    if new_session_id:
                        self._session_map[session_id] = new_session_id

                    await self._bus.emit(
                        ResponseStart(
                            user_id=user_id,
                            mode=self.name,
                            session_id=session_id,
                            chat_id=context.chat_id,
                        )
                    )

                    async for line in response.aiter_lines():
                        if not line or not line.startswith("data: "):
                            continue

                        data_str = line[6:]
                        if data_str == "[DONE]":
                            break

                        try:
                            payload = cast(object, json.loads(data_str))
                        except json.JSONDecodeError:
                            continue

                        if not _is_dict(payload):
                            continue

                        choices = payload.get("choices")
                        if not _is_list(choices):
                            continue

                        first_choice = choices[0] if choices else None
                        if not _is_dict(first_choice):
                            continue

                        delta = first_choice.get("delta")
                        if not _is_dict(delta):
                            continue

                        content = delta.get("content")
                        if not isinstance(content, str):
                            continue
                        if content:
                            full_response += content
                            await self._bus.emit(
                                ResponseChunk(
                                    user_id=user_id,
                                    mode=self.name,
                                    session_id=session_id,
                                    text=content,
                                )
                            )

            elapsed = time.monotonic() - start_time
            await self._bus.emit(
                ResponseEnd(
                    user_id=user_id,
                    mode=self.name,
                    session_id=session_id,
                    full_text=full_response,
                    elapsed=elapsed,
                    chat_id=context.chat_id,
                )
            )
            return full_response
        except Exception as exc:
            await self._bus.emit(
                ResponseError(
                    user_id=user_id,
                    mode=self.name,
                    session_id=session_id,
                    error=str(exc),
                    chat_id=context.chat_id,
                )
            )
            raise

    async def destroy_session(self, session_id: str) -> None:
        _ = self._session_map.pop(session_id, None)

    def clear_session(self, chat_key: str) -> None:
        _ = self._session_map.pop(chat_key, None)


def _is_dict(value: object) -> TypeGuard[dict[str, object]]:
    return isinstance(value, dict)


def _is_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)
