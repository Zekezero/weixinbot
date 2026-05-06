"""19.7 测试 OpenCodeAdapter SSE 事件序列"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from weixin_bot.config import WeixinBotConfig
from weixin_bot.modes.adapters.opencode import (
    OpenCodeAdapter,
    PermissionRequest,
    classify_event,
    EventPriority,
    format_permission,
    format_error,
    _format_tool_label,
)
from weixin_bot.modes.events import (
    EventBus,
    ResponseChunk,
    ResponseEnd,
    ResponseError,
    ResponseStart,
)
from weixin_bot.modes.adapter import MessageContext


def _make_config() -> WeixinBotConfig:
    return WeixinBotConfig(opencode_base_url="http://localhost:29107")


def _make_context() -> MessageContext:
    return MessageContext(chat_type="direct", sender_id="u1", chat_id="c1")


class TestEventClassification:
    def test_permission_is_critical(self) -> None:
        assert classify_event("permission.updated", {}) == EventPriority.CRITICAL

    def test_session_error_is_critical(self) -> None:
        assert classify_event("session.error", {}) == EventPriority.CRITICAL

    def test_session_idle_is_critical(self) -> None:
        assert classify_event("session.idle", {}) == EventPriority.CRITICAL

    def test_delta_with_text_is_streaming(self) -> None:
        assert classify_event("message.part.delta", {"delta": "hi"}) == EventPriority.STREAMING

    def test_delta_without_text_is_ignored(self) -> None:
        assert classify_event("message.part.delta", {}) == EventPriority.IGNORED

    def test_tool_updated_is_streaming(self) -> None:
        props = {"part": {"type": "tool"}}
        assert classify_event("message.part.updated", props) == EventPriority.STREAMING

    def test_unknown_is_ignored(self) -> None:
        assert classify_event("some.random.event", {}) == EventPriority.IGNORED


class TestEventFormatting:
    def test_format_permission_with_title(self) -> None:
        result = format_permission({"title": "Write to file.py", "type": "write"})
        assert "Write to file.py" in result
        assert "/approve" in result

    def test_format_error_string(self) -> None:
        result = format_error({"error": "timeout"})
        assert "timeout" in result

    def test_format_error_dict(self) -> None:
        result = format_error({"error": {"name": "RateLimit", "data": {"message": "too fast"}}})
        assert "too fast" in result

    def test_tool_label_read(self) -> None:
        label = _format_tool_label("read", {"filePath": "/src/main.py"})
        assert "Read" in label
        assert "main.py" in label

    def test_tool_label_bash(self) -> None:
        label = _format_tool_label("bash", {"command": "ls -la"})
        assert "ls -la" in label

    def test_tool_label_no_input(self) -> None:
        label = _format_tool_label("read", {})
        assert "Reading" in label


class TestOpenCodeAdapterSSE:
    @pytest.mark.asyncio
    async def test_normal_flow(self) -> None:
        """send → SSE deltas → session.idle → ResponseStart/Chunk/End"""
        bus = EventBus()
        events: list[object] = []
        bus.on(ResponseStart, lambda e: _collect(events, e))
        bus.on(ResponseChunk, lambda e: _collect(events, e))
        bus.on(ResponseEnd, lambda e: _collect(events, e))

        adapter = OpenCodeAdapter(_make_config(), bus)
        adapter._sse_started = True  # skip SSE connection

        # Mock prompt_async
        with patch.object(adapter, "_http_client") as mock_client_factory:
            mock_client = AsyncMock()
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client_factory.return_value = mock_client

            with patch.object(adapter._sse, "register"):
                await adapter.send("sess1", "hello", _make_context(), user_id="u1")

        # Verify ResponseStart emitted
        assert any(isinstance(e, ResponseStart) for e in events)

        # Simulate SSE events
        await adapter._on_sse_event("message.part.delta", {
            "sessionID": "sess1", "delta": "Hello ", "field": "text",
        })
        await adapter._on_sse_event("message.part.delta", {
            "sessionID": "sess1", "delta": "world!", "field": "text",
        })

        chunks = [e for e in events if isinstance(e, ResponseChunk)]
        assert len(chunks) == 2
        assert chunks[0].text == "Hello "
        assert chunks[1].text == "world!"

        # session.idle → End
        with patch.object(adapter, "_fetch_diff", return_value="+10 -2 (3 files)"):
            await adapter._on_sse_event("session.idle", {"sessionID": "sess1"})

        ends = [e for e in events if isinstance(e, ResponseEnd)]
        assert len(ends) == 1

    @pytest.mark.asyncio
    async def test_abort_ignores_subsequent_events(self) -> None:
        """abort 后 SSE 事件被忽略"""
        bus = EventBus()
        events: list[object] = []
        bus.on(ResponseChunk, lambda e: _collect(events, e))

        adapter = OpenCodeAdapter(_make_config(), bus)
        adapter._sse_started = True
        adapter._oc_to_user["sess1"] = "u1"
        adapter._oc_to_chat["sess1"] = "c1"
        adapter._oc_to_session["sess1"] = "sess1"
        adapter._busy_users.add("u1")

        # Simulate abort
        with patch.object(adapter, "_http_client") as mock_cf:
            mc = AsyncMock()
            mr = MagicMock()
            mr.status_code = 200
            mr.text = "ok"
            mc.post = AsyncMock(return_value=mr)
            mc.__aenter__ = AsyncMock(return_value=mc)
            mc.__aexit__ = AsyncMock(return_value=False)
            mock_cf.return_value = mc
            result = await adapter.abort("u1")

        assert result == "任务已中止"

        # Subsequent SSE events should be ignored
        await adapter._on_sse_event("message.part.delta", {
            "sessionID": "sess1", "delta": "should be ignored",
        })
        assert len(events) == 0

    @pytest.mark.asyncio
    async def test_abort_no_session(self) -> None:
        """abort 无活跃会话"""
        bus = EventBus()
        adapter = OpenCodeAdapter(_make_config(), bus)
        result = await adapter.abort("unknown_user")
        assert result == "未找到活跃会话"

    @pytest.mark.asyncio
    async def test_permission_flow(self) -> None:
        """permission.updated → PermissionRequest event"""
        bus = EventBus()
        events: list[object] = []
        bus.on(PermissionRequest, lambda e: _collect(events, e))

        adapter = OpenCodeAdapter(_make_config(), bus)
        adapter._oc_to_user["sess1"] = "u1"
        adapter._oc_to_chat["sess1"] = "c1"
        adapter._oc_to_session["sess1"] = "sess1"
        adapter._busy_users.add("u1")

        await adapter._on_sse_event("permission.updated", {
            "sessionID": "sess1",
            "id": "perm_001",
            "title": "Write to config.py",
            "type": "write",
        })

        assert len(events) == 1
        perm = events[0]
        assert isinstance(perm, PermissionRequest)
        assert perm.permission_id == "perm_001"
        assert "config.py" in perm.description

    @pytest.mark.asyncio
    async def test_session_error(self) -> None:
        """session.error → ResponseError"""
        bus = EventBus()
        events: list[object] = []
        bus.on(ResponseError, lambda e: _collect(events, e))

        adapter = OpenCodeAdapter(_make_config(), bus)
        adapter._oc_to_user["sess1"] = "u1"
        adapter._oc_to_chat["sess1"] = "c1"
        adapter._oc_to_session["sess1"] = "sess1"
        adapter._busy_users.add("u1")

        await adapter._on_sse_event("session.error", {
            "sessionID": "sess1",
            "error": "rate limit exceeded",
        })

        assert len(events) == 1
        assert "rate limit" in events[0].error

    @pytest.mark.asyncio
    async def test_tool_display(self) -> None:
        """tool.start/end → ResponseChunk(channel=main)"""
        bus = EventBus()
        events: list[object] = []
        bus.on(ResponseChunk, lambda e: _collect(events, e))

        adapter = OpenCodeAdapter(_make_config(), bus)
        adapter._oc_to_user["sess1"] = "u1"
        adapter._oc_to_chat["sess1"] = "c1"
        adapter._oc_to_session["sess1"] = "sess1"
        adapter._busy_users.add("u1")

        await adapter._on_sse_event("message.part.updated", {
            "sessionID": "sess1",
            "part": {
                "type": "tool",
                "tool": "read",
                "sessionID": "sess1",
                "state": {
                    "status": "running",
                    "input": {"filePath": "/src/main.py"},
                },
            },
        })

        assert len(events) == 1
        assert "Read" in events[0].text
        assert events[0].channel == "main"

    @pytest.mark.asyncio
    async def test_busy_user_message_dropped(self) -> None:
        """忙碌用户消息被丢弃"""
        bus = EventBus()
        adapter = OpenCodeAdapter(_make_config(), bus)
        adapter._sse_started = True
        adapter._busy_users.add("u1")

        result = await adapter.send("sess1", "ignored", _make_context(), user_id="u1")
        assert result == ""


async def _collect(lst: list[object], event: object) -> None:
    lst.append(event)
