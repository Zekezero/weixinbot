"""Agent 适配器抽象接口"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from weixin_bot.modes.events import EventBus


# ── 数据类 ────────────────────────────────────────────


@dataclass
class MessageContext:
    """消息上下文 — 传递给 Adapter 的元数据"""

    chat_type: str  # "direct" | "group"
    sender_id: str
    chat_id: str
    file_ids: list[str] = field(default_factory=list)
    image_urls: list[str] = field(default_factory=list)


@dataclass
class SessionInfo:
    """Agent 会话摘要"""

    session_id: str
    title: str = ""
    created_at: str = ""


# ── 抽象接口 ──────────────────────────────────────────


class AgentAdapter(ABC):
    """Agent 后端适配器 — 纯协议翻译层

    每个 Agent 后端实现一个子类。Adapter 只负责:
    - 创建/恢复/销毁 Agent 会话
    - 发送消息并流式返回回复
    - 通过 EventBus 发射事件

    Adapter 不负责 UI 渲染、会话持久化或业务逻辑。
    """

    name: str  # "hermes"
    display_name: str  # "Hermes Agent"

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    @abstractmethod
    async def create_session(self) -> str:
        """创建新会话，返回 session_id"""
        ...

    @abstractmethod
    async def send(
        self,
        session_id: str,
        message: str,
        context: MessageContext,
        *,
        user_id: str,
    ) -> str:
        """发送消息到 Agent，流式通过 EventBus 发射事件。

        返回完整响应文本。
        """
        ...

    @abstractmethod
    async def destroy_session(self, session_id: str) -> None:
        """销毁指定会话"""
        ...

    async def list_sessions(self) -> list[SessionInfo]:
        """列出历史会话 (可选实现)"""
        return []
