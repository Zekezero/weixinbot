"""事件处理器注册表 — 装饰器模式"""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Awaitable, Callable

from weixin_bot.models import EventType, IncomingEvent, MsgType

logger = logging.getLogger("weixin_bot.handler")

EventHandler = Callable[[IncomingEvent], Awaitable[None]]
MessageFilter = Callable[[IncomingEvent], bool]


class HandlerRegistry:
    """事件处理器注册表

    支持按事件类型注册处理函数，支持消息过滤器。
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[tuple[EventHandler, MessageFilter | None]]] = defaultdict(
            list
        )

    def on(
        self,
        event_type: str,
        *,
        filter_fn: MessageFilter | None = None,
    ) -> Callable[[EventHandler], EventHandler]:
        """注册指定事件类型的处理器"""
        def decorator(fn: EventHandler) -> EventHandler:
            self._handlers[str(event_type)].append((fn, filter_fn))
            logger.debug("注册处理器: %s -> %s", event_type, fn.__name__)
            return fn
        return decorator

    def on_message(
        self,
        *,
        msg_types: list[MsgType | int] | None = None,
        p2p_only: bool = False,
        group_only: bool = False,
    ) -> Callable[[EventHandler], EventHandler]:
        """注册消息处理器"""
        def _filter(event: IncomingEvent) -> bool:
            msg = event.as_message()
            if p2p_only and not msg.is_p2p:
                return False
            if group_only and not msg.is_group:
                return False
            return True

        filter_fn = _filter if (msg_types or p2p_only or group_only) else None

        def decorator(fn: EventHandler) -> EventHandler:
            # 微信当前仅 P2P，但注册两种以备未来扩展
            if not group_only:
                self._handlers[EventType.P2P_MESSAGE].append((fn, filter_fn))
            logger.debug("注册消息处理器: %s", fn.__name__)
            return fn

        return decorator

    def on_recall(self) -> Callable[[EventHandler], EventHandler]:
        """注册撤回事件处理器（预留）"""
        def decorator(fn: EventHandler) -> EventHandler:
            self._handlers["p2p_recall"].append((fn, None))
            return fn
        return decorator

    async def dispatch(self, event: IncomingEvent) -> None:
        """分发事件到匹配的处理器"""
        handlers = self._handlers.get(event.event_type, [])
        if not handlers:
            logger.debug("无处理器匹配事件: %s", event.event_type)
            return

        for handler_fn, filter_fn in handlers:
            try:
                if filter_fn is not None and not filter_fn(event):
                    continue
                await handler_fn(event)
            except Exception:
                logger.exception("处理器 %s 执行失败", handler_fn.__name__)
