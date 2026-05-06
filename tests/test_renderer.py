"""19.8 测试 TextRenderer 节流与分段发送"""

import asyncio

import pytest

from weixin_bot.modes.events import EventBus, ResponseChunk, ResponseEnd, ResponseError, ResponseStart
from weixin_bot.modes.renderer import RendererConfig, TextRenderer


class _SendCollector:
    """收集所有发送的消息"""

    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    async def __call__(self, chat_id: str, text: str) -> None:
        self.messages.append((chat_id, text))


def _make_renderer(
    push_interval: float = 0.1,
    push_min_chars: int = 50,
    max_message_chars: int = 200,
) -> tuple[TextRenderer, EventBus, _SendCollector]:
    bus = EventBus()
    collector = _SendCollector()
    config = RendererConfig(
        push_interval=push_interval,
        push_min_chars=push_min_chars,
        max_message_chars=max_message_chars,
    )
    renderer = TextRenderer(collector, bus, config)
    return renderer, bus, collector


class TestTextRenderer:
    @pytest.mark.asyncio
    async def test_simple_flow(self) -> None:
        """ResponseStart → Chunk → End → 发送完整文本"""
        _, bus, collector = _make_renderer()

        await bus.emit(ResponseStart(user_id="u1", mode="test", session_id="s1", chat_id="c1"))
        await bus.emit(ResponseChunk(user_id="u1", mode="test", session_id="s1", text="Hello"))
        await bus.emit(ResponseEnd(user_id="u1", mode="test", session_id="s1", chat_id="c1"))

        assert len(collector.messages) >= 1
        all_text = "".join(t for _, t in collector.messages)
        assert "Hello" in all_text

    @pytest.mark.asyncio
    async def test_error_sends_message(self) -> None:
        _, bus, collector = _make_renderer()

        await bus.emit(ResponseStart(user_id="u1", mode="test", session_id="s1", chat_id="c1"))
        await bus.emit(ResponseError(user_id="u1", mode="test", session_id="s1", error="boom", chat_id="c1"))

        assert len(collector.messages) == 1
        assert "boom" in collector.messages[0][1]

    @pytest.mark.asyncio
    async def test_fulltext_fallback_on_empty_buffer(self) -> None:
        """无 chunk 时用 full_text 兜底"""
        _, bus, collector = _make_renderer()

        await bus.emit(ResponseStart(user_id="u1", mode="test", session_id="s1", chat_id="c1"))
        await bus.emit(ResponseEnd(
            user_id="u1", mode="test", session_id="s1",
            full_text="fallback text", chat_id="c1",
        ))

        assert any("fallback text" in t for _, t in collector.messages)

    @pytest.mark.asyncio
    async def test_split_long_text(self) -> None:
        """超长文本被切分 (End flush path)"""
        # push_min_chars=999 prevents intermediate push; split happens in End
        _, bus, collector = _make_renderer(push_min_chars=999, max_message_chars=50)

        await bus.emit(ResponseStart(user_id="u1", mode="test", session_id="s1", chat_id="c1"))
        long_text = "A" * 120
        await bus.emit(ResponseChunk(user_id="u1", mode="test", session_id="s1", text=long_text))
        await bus.emit(ResponseEnd(user_id="u1", mode="test", session_id="s1", chat_id="c1"))

        # 120 chars / 50 max = 3 messages
        assert len(collector.messages) == 3
        total = sum(len(t) for _, t in collector.messages)
        assert total == 120

    @pytest.mark.asyncio
    async def test_multichannel_merged(self) -> None:
        """非 main channel 的 chunk 合并到输出"""
        _, bus, collector = _make_renderer()

        await bus.emit(ResponseStart(user_id="u1", mode="test", session_id="s1", chat_id="c1"))
        await bus.emit(ResponseChunk(user_id="u1", mode="test", session_id="s1", text="main text", channel="main"))
        await bus.emit(ResponseChunk(user_id="u1", mode="test", session_id="s1", text=" tool output", channel="tool"))
        await bus.emit(ResponseEnd(user_id="u1", mode="test", session_id="s1", chat_id="c1"))

        all_text = "".join(t for _, t in collector.messages)
        assert "main text" in all_text
        assert "tool output" in all_text


class TestSplitText:
    def test_short_text(self) -> None:
        result = TextRenderer._split_text("hello", 100)
        assert result == ["hello"]

    def test_split_at_double_newline(self) -> None:
        text = "first paragraph\n\nsecond paragraph"
        result = TextRenderer._split_text(text, 20)
        assert len(result) == 2
        assert "first" in result[0]
        assert "second" in result[1]

    def test_split_at_single_newline(self) -> None:
        text = "line one\nline two that is longer"
        result = TextRenderer._split_text(text, 15)
        assert len(result) >= 2

    def test_hard_split(self) -> None:
        text = "A" * 100
        result = TextRenderer._split_text(text, 30)
        assert all(len(chunk) <= 30 for chunk in result)
        assert "".join(result) == text
