"""可插拔渲染器 — 事件驱动输出

BaseRenderer 抽象接口 + TextRenderer 默认实现。
未来微信支持卡片消息时，可快速实现 CardRenderer 替换。
"""

from __future__ import annotations

import logging
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from weixin_bot.modes.events import (
    EventBus,
    ModeEntered,
    ModeEvent,
    ModeExited,
    ResponseChunk,
    ResponseEnd,
    ResponseError,
    ResponseStart,
)

logger = logging.getLogger("weixin_bot.modes.renderer")

SendFunction = Callable[[str, str], Awaitable[None]]  # (chat_id, text) -> None

# 文件标记正则: [image: xxx] / [file: xxx]
_FILE_MARKER_RE = re.compile(r"\[(?:image|file):\s*[^\]]+\]", re.IGNORECASE)
_PARTIAL_MARKER_RE = re.compile(r"\[(?:image|file)(?::\s*[^\]]*)?$", re.IGNORECASE)


@dataclass
class RendererConfig:
    """渲染器配置"""

    push_interval: float = 3.0  # 秒，中间推送间隔
    push_min_chars: int = 2000  # 最小推送字符数
    max_message_chars: int = 3000  # 单条消息最大字符数
    renderer_type: str = "text"


# ── 抽象基类 ──────────────────────────────────────────


class BaseRenderer(ABC):
    """可插拔渲染器抽象基类

    通过 EventBus 事件驱动。子类实现 on_response_* 方法。
    """

    def __init__(self, send_fn: SendFunction, bus: EventBus, config: RendererConfig) -> None:
        self._send_fn = send_fn
        self._bus = bus
        self._config = config
        # 订阅 EventBus
        bus.on(ResponseStart, self._handle_start)
        bus.on(ResponseChunk, self._handle_chunk)
        bus.on(ResponseEnd, self._handle_end)
        bus.on(ResponseError, self._handle_error)

    async def close(self) -> None:
        """关闭渲染器，清理资源"""
        pass

    async def _handle_start(self, event: ModeEvent) -> None:
        if isinstance(event, ResponseStart):
            await self.on_response_start(event)

    async def _handle_chunk(self, event: ModeEvent) -> None:
        if isinstance(event, ResponseChunk):
            await self.on_response_chunk(event)

    async def _handle_end(self, event: ModeEvent) -> None:
        if isinstance(event, ResponseEnd):
            await self.on_response_end(event)

    async def _handle_error(self, event: ModeEvent) -> None:
        if isinstance(event, ResponseError):
            await self.on_response_error(event)

    @abstractmethod
    async def on_response_start(self, event: ResponseStart) -> None: ...

    @abstractmethod
    async def on_response_chunk(self, event: ResponseChunk) -> None: ...

    @abstractmethod
    async def on_response_end(self, event: ResponseEnd) -> None: ...

    @abstractmethod
    async def on_response_error(self, event: ResponseError) -> None: ...


# ── TextRenderer 默认实现 ────────────────────────────


@dataclass
class _TextState:
    """单用户文本渲染状态"""

    chat_id: str = ""
    buffer: str = ""
    last_push: float = 0.0
    last_pushed_len: int = 0
    has_sent_intermediate: bool = False
    pending_marker: str = ""


class TextRenderer(BaseRenderer):
    """文本渲染器 — 将流式响应转为分段文本消息

    行为:
    - ResponseChunk: 累积到 buffer，按时间/字符节流中间发送
    - ResponseEnd: flush 剩余 buffer，按段落边界切分
    - ResponseError: 发送错误文本
    - 所有通道合并到单一输出（微信当前限制）
    """

    def __init__(self, send_fn: SendFunction, bus: EventBus, config: RendererConfig) -> None:
        super().__init__(send_fn, bus, config)
        self._active: dict[str, _TextState] = {}  # user_id → state

    async def on_response_start(self, event: ResponseStart) -> None:
        self._active[event.user_id] = _TextState(
            chat_id=event.chat_id,
            last_push=time.monotonic(),
        )

    async def on_response_chunk(self, event: ResponseChunk) -> None:
        state = self._active.get(event.user_id)
        if not state:
            return

        state.buffer += event.text

        if self._should_push(state):
            await self._push_intermediate(state)

    async def on_response_end(self, event: ResponseEnd) -> None:
        state = self._active.pop(event.user_id, None)

        # 兜底: 如果没有状态但有 full_text，直接发送
        if not state:
            if event.full_text and event.chat_id:
                await self._send_text_split(event.chat_id, event.full_text)
            return

        # flush 剩余 buffer
        remaining = state.pending_marker + state.buffer[state.last_pushed_len:]
        remaining = _FILE_MARKER_RE.sub("", remaining).strip()

        if remaining:
            await self._send_text_split(state.chat_id, remaining)
        elif not state.has_sent_intermediate and event.full_text:
            # 从未发送过任何内容，用 full_text 兜底
            await self._send_text_split(state.chat_id, event.full_text)

    async def on_response_error(self, event: ResponseError) -> None:
        state = self._active.pop(event.user_id, None)
        chat_id = event.chat_id or (state.chat_id if state else "")
        if chat_id and event.error:
            try:
                await self._send_fn(chat_id, f"⚠ {event.error}")
            except Exception:
                logger.exception("发送错误消息失败")

    # ── 节流逻辑 ──────────────────────────────────

    def _should_push(self, state: _TextState) -> bool:
        now = time.monotonic()
        elapsed = now - state.last_push
        new_chars = len(state.buffer) - state.last_pushed_len
        return (
            elapsed >= self._config.push_interval
            or new_chars >= self._config.push_min_chars
        )

    async def _push_intermediate(self, state: _TextState) -> None:
        """推送中间文本"""
        raw = state.pending_marker + state.buffer[state.last_pushed_len:]
        state.pending_marker = ""

        # 过滤文件标记
        clean = _FILE_MARKER_RE.sub("", raw)

        # 检查未闭合标记
        match = _PARTIAL_MARKER_RE.search(clean)
        if match and match.end() == len(clean):
            state.pending_marker = clean[match.start():]
            clean = clean[:match.start()]

        if not clean.strip():
            return

        try:
            await self._send_fn(state.chat_id, clean)
            state.has_sent_intermediate = True
        except Exception:
            logger.exception("中间发送失败")

        state.last_push = time.monotonic()
        state.last_pushed_len = len(state.buffer)

    # ── 文本切分 ──────────────────────────────────

    async def _send_text_split(self, chat_id: str, text: str) -> None:
        """按段落边界切分发送"""
        if not text:
            return
        for chunk in self._split_text(text, self._config.max_message_chars):
            try:
                await self._send_fn(chat_id, chunk)
            except Exception:
                logger.exception("发送文本失败")

    @staticmethod
    def _split_text(text: str, limit: int) -> list[str]:
        """按段落优先切分文本"""
        chunks: list[str] = []
        remaining = text

        while remaining:
            if len(remaining) <= limit:
                chunks.append(remaining)
                break

            # 优先在双换行处切分
            cut = remaining.rfind("\n\n", 0, limit + 1)
            if cut == -1:
                cut = remaining.rfind("\n", 0, limit + 1)
            if cut == -1:
                cut = limit

            chunks.append(remaining[:cut])
            remaining = remaining[cut:]
            if remaining.startswith("\n"):
                remaining = remaining.lstrip("\n")

        return chunks
