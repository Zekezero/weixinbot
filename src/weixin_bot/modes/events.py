"""模式事件类型与事件总线"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Awaitable, Callable

logger = logging.getLogger("weixin_bot.modes.events")


# ── 事件类型 ──────────────────────────────────────────


@dataclass
class ModeEvent:
    """模式事件基类"""

    user_id: str
    mode: str
    session_id: str


@dataclass
class ModeEntered(ModeEvent):
    """用户进入模式"""


@dataclass
class ModeExited(ModeEvent):
    """用户退出模式"""


@dataclass
class ResponseStart(ModeEvent):
    """Agent 开始响应"""

    chat_id: str = ""


@dataclass
class ResponseChunk(ModeEvent):
    """Agent 响应的一个文本片段"""

    text: str = ""
    channel: str = "main"


@dataclass
class ResponseEnd(ModeEvent):
    """Agent 响应结束"""

    full_text: str = ""
    elapsed: float = 0.0
    chat_id: str = ""


@dataclass
class ResponseError(ModeEvent):
    """Agent 响应出错"""

    error: str = ""
    chat_id: str = ""


# ── 事件总线 ──────────────────────────────────────────

EventHandler = Callable[[ModeEvent], Awaitable[None]]


class EventBus:
    """极简事件总线 — 发布/订阅模式

    Adapter emit 事件，Renderer 订阅并渲染。handler 异常不阻断其他 handler。
    """

    def __init__(self) -> None:
        self._handlers: dict[type, list[EventHandler]] = defaultdict(list)

    def on(self, event_type: type, handler: EventHandler) -> None:
        """注册事件处理器"""
        self._handlers[event_type].append(handler)

    async def emit(self, event: ModeEvent) -> None:
        """分发事件到所有注册的处理器，异常隔离"""
        for handler in self._handlers.get(type(event), []):
            try:
                await handler(event)
            except Exception:
                logger.exception(
                    "事件处理器 %s 执行失败 (event=%s)",
                    handler.__name__ if hasattr(handler, "__name__") else handler,
                    type(event).__name__,
                )
