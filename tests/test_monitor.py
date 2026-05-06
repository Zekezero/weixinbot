"""19.4 测试长轮询重试逻辑"""

import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from weixin_bot.client import WeixinClient
from weixin_bot.errors import SessionExpiredError
from weixin_bot.monitor import (
    BACKOFF_DELAY_S,
    MAX_CONSECUTIVE_FAILURES,
    RETRY_DELAY_S,
    SESSION_PAUSE_DURATION_S,
    WeixinMonitor,
)


def _make_monitor(on_message: AsyncMock | None = None) -> WeixinMonitor:
    client = WeixinClient(token="test", account_id="test-account")
    return WeixinMonitor(
        client=client,
        state_dir=Path("/tmp/weixinbot-test"),
        on_message=on_message or AsyncMock(),
    )


class TestRetryLogic:
    def test_consecutive_failure_counter(self) -> None:
        monitor = _make_monitor()
        assert monitor._consecutive_failures == 0
        monitor._consecutive_failures = 2
        assert monitor._consecutive_failures == 2

    def test_session_pause(self) -> None:
        monitor = _make_monitor()
        assert monitor._session_pause_until == 0
        monitor._pause_session()
        assert monitor._session_pause_until > time.time()
        remaining = monitor._session_pause_until - time.time()
        assert remaining > 3500  # ~1 hour

    @pytest.mark.asyncio
    async def test_poll_once_normal_timeout(self) -> None:
        """正常超时不算失败"""
        monitor = _make_monitor()
        with patch.object(monitor._api, "get_updates", side_effect=asyncio.TimeoutError):
            await monitor._poll_once()
        assert monitor._consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_poll_once_session_expired(self) -> None:
        """errcode=-14 触发 SessionExpiredError"""
        monitor = _make_monitor()
        with patch.object(monitor._api, "get_updates", return_value={
            "ret": 0, "errcode": -14, "errmsg": "session expired",
        }):
            with pytest.raises(SessionExpiredError):
                await monitor._poll_once()

    @pytest.mark.asyncio
    async def test_poll_once_success_resets_failures(self) -> None:
        """成功响应重置连续失败计数"""
        monitor = _make_monitor()
        monitor._consecutive_failures = 2
        with patch.object(monitor._api, "get_updates", return_value={
            "ret": 0, "errcode": 0, "msgs": [], "get_updates_buf": "buf1",
        }):
            await monitor._poll_once()
        assert monitor._consecutive_failures == 0

    @pytest.mark.asyncio
    async def test_poll_once_dispatches_messages(self) -> None:
        """收到消息分发到回调"""
        on_msg = AsyncMock()
        monitor = _make_monitor(on_msg)
        msg = {"message_id": "123", "from_user_id": "u1", "context_token": "ct1", "item_list": []}
        with patch.object(monitor._api, "get_updates", return_value={
            "ret": 0, "errcode": 0, "msgs": [msg], "get_updates_buf": "buf2",
        }):
            await monitor._poll_once()
        on_msg.assert_called_once_with(msg)

    @pytest.mark.asyncio
    async def test_context_token_cached(self) -> None:
        """context_token 被缓存"""
        monitor = _make_monitor()
        msg = {"message_id": "456", "from_user_id": "u2", "context_token": "ctx_abc"}
        with patch.object(monitor._api, "get_updates", return_value={
            "ret": 0, "errcode": 0, "msgs": [msg], "get_updates_buf": "buf3",
        }):
            await monitor._poll_once()
        assert monitor.get_context_token("u2") == "ctx_abc"

    @pytest.mark.asyncio
    async def test_server_timeout_respected(self) -> None:
        """服务端建议超时被采纳"""
        monitor = _make_monitor()
        with patch.object(monitor._api, "get_updates", return_value={
            "ret": 0, "errcode": 0, "msgs": [],
            "longpolling_timeout_ms": 60000,
        }):
            await monitor._poll_once()
        assert monitor._next_poll_timeout_ms == 60000
