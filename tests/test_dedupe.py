"""19.5 测试消息去重（LRU 缓存命中/过期）"""

import time
from unittest.mock import AsyncMock, patch

from weixin_bot.monitor import WeixinMonitor


def _make_monitor() -> WeixinMonitor:
    from pathlib import Path

    from weixin_bot.client import WeixinClient

    client = WeixinClient(token="test", account_id="test-account")
    return WeixinMonitor(
        client=client,
        state_dir=Path("/tmp/weixinbot-test"),
        on_message=AsyncMock(),
    )


class TestMessageDedupe:
    def test_first_seen_not_duplicate(self) -> None:
        monitor = _make_monitor()
        assert monitor._is_duplicate("msg_001") is False

    def test_second_seen_is_duplicate(self) -> None:
        monitor = _make_monitor()
        monitor._is_duplicate("msg_001")
        assert monitor._is_duplicate("msg_001") is True

    def test_different_ids_not_duplicate(self) -> None:
        monitor = _make_monitor()
        monitor._is_duplicate("msg_001")
        assert monitor._is_duplicate("msg_002") is False

    def test_empty_id_never_duplicate(self) -> None:
        monitor = _make_monitor()
        assert monitor._is_duplicate("") is False
        assert monitor._is_duplicate("") is False

    def test_expired_entry_not_duplicate(self) -> None:
        monitor = _make_monitor()
        monitor._is_duplicate("msg_old")
        # Simulate 31 minutes passing
        monitor._seen_msg_ids["msg_old"] = time.time() - 1860
        assert monitor._is_duplicate("msg_old") is False

    def test_capacity_limit(self) -> None:
        monitor = _make_monitor()
        # Fill cache to capacity
        for i in range(10001):
            monitor._is_duplicate(f"msg_{i}")
        # First entries should be evicted
        assert len(monitor._seen_msg_ids) <= 10000
