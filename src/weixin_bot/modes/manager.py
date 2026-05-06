"""模式管理器 — 维护用户会话与转发"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from weixin_bot.models import IncomingEvent, WeixinMsgDTO

from .adapter import AgentAdapter, MessageContext
from .events import EventBus, ModeEntered, ModeExited


@dataclass
class _ModeState:
    """用户当前模式状态"""

    mode_name: str
    session_id: str


class ModeManager:
    def __init__(self, bus: EventBus):
        self._bus = bus
        self._adapters: dict[str, AgentAdapter] = {}  # name → adapter
        self._user_modes: dict[str, _ModeState] = {}  # user_id → state
        self._locks: dict[str, asyncio.Lock] = {}  # chat_key → lock

    def register_adapter(self, adapter: AgentAdapter) -> None:
        self._adapters[adapter.name] = adapter

    def get_adapter(self, name: str) -> AgentAdapter | None:
        return self._adapters.get(name)

    def get_user_mode(self, user_id: str) -> _ModeState | None:
        return self._user_modes.get(user_id)

    def is_in_mode(self, user_id: str) -> bool:
        return user_id in self._user_modes

    async def enter_mode(
        self, user_id: str, mode_name: str, session_id: str | None = None
    ) -> str:
        adapter = self.get_adapter(mode_name)
        if not adapter:
            raise ValueError(f"未知模式: {mode_name}")

        if session_id is None:
            session_id = await adapter.create_session()

        self._user_modes[user_id] = _ModeState(mode_name=mode_name, session_id=session_id)

        await self._bus.emit(
            ModeEntered(user_id=user_id, mode=mode_name, session_id=session_id)
        )

        return session_id

    async def exit_mode(self, user_id: str) -> None:
        state = self._user_modes.pop(user_id, None)
        if not state:
            return

        # 清理 adapter 资源
        adapter = self.get_adapter(state.mode_name)
        if adapter:
            try:
                await adapter.destroy_session(state.session_id)
            except Exception:
                pass  # best-effort cleanup

        await self._bus.emit(
            ModeExited(user_id=user_id, mode=state.mode_name, session_id=state.session_id)
        )

    async def new_session(self, user_id: str) -> str:
        state = self._user_modes.get(user_id)
        if not state:
            raise ValueError("当前用户未进入任何模式")

        adapter = self.get_adapter(state.mode_name)
        if not adapter:
            raise ValueError(f"未知模式: {state.mode_name}")

        session_id = await adapter.create_session()
        state.session_id = session_id
        return session_id

    async def try_forward(self, event: IncomingEvent) -> bool:
        if not event.is_message:
            return False

        msg = event.as_message()
        user_id = msg.from_
        state = self._user_modes.get(user_id)
        if not state:
            return False

        adapter = self.get_adapter(state.mode_name)
        if not adapter:
            return False

        context = self._build_context(msg)
        chat_key = self._chat_key(msg)
        lock = self._locks.setdefault(chat_key, asyncio.Lock())

        async with lock:
            await adapter.send(state.session_id, msg.text, context, user_id=user_id)

        return True

    def _build_context(self, msg: WeixinMsgDTO) -> MessageContext:
        chat_type = "direct" if msg.is_p2p else "group"
        return MessageContext(
            chat_type=chat_type,
            sender_id=msg.from_,
            chat_id=msg.session_id,
            file_ids=[],
            image_urls=[],
        )

    def _chat_key(self, msg: WeixinMsgDTO) -> str:
        if msg.is_p2p:
            return f"direct:{msg.from_}"
        return f"group:{msg.session_id}:{msg.from_}"
