"""19.3 测试 QR 登录状态机（mock API 响应）"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from weixin_bot.auth import qr_login
from weixin_bot.client import WeixinClient
from weixin_bot.errors import AuthError


class TestQRLogin:
    @pytest.mark.asyncio
    async def test_confirmed_immediately(self) -> None:
        client = WeixinClient()
        client._client = MagicMock()

        with patch("weixin_bot.auth.WeixinAPI") as MockAPI:
            api = MockAPI.return_value
            api.get_bot_qrcode = AsyncMock(return_value={
                "qrcode": "test_qr_123",
                "qrcode_img_content": "https://example.com/qr.png",
            })
            api.get_qrcode_status = AsyncMock(return_value={
                "status": "confirmed",
                "bot_token": "tok_abc",
                "ilink_bot_id": "bot_001",
                "baseurl": "https://ilink.example.com",
            })

            with patch("weixin_bot.auth._display_qr"):
                result = await qr_login(client)

        assert result["token"] == "tok_abc"
        assert result["accountId"] == "bot_001"

    @pytest.mark.asyncio
    async def test_wait_then_confirmed(self) -> None:
        client = WeixinClient()
        client._client = MagicMock()

        responses = [
            {"status": "wait"},
            {"status": "scaned"},
            {"status": "confirmed", "bot_token": "tok", "ilink_bot_id": "b1"},
        ]

        with patch("weixin_bot.auth.WeixinAPI") as MockAPI:
            api = MockAPI.return_value
            api.get_bot_qrcode = AsyncMock(return_value={"qrcode": "qr1"})
            api.get_qrcode_status = AsyncMock(side_effect=responses)

            with patch("weixin_bot.auth._display_qr"):
                result = await qr_login(client)

        assert result["token"] == "tok"

    @pytest.mark.asyncio
    async def test_expired_then_refresh(self) -> None:
        client = WeixinClient()
        client._client = MagicMock()

        with patch("weixin_bot.auth.WeixinAPI") as MockAPI:
            api = MockAPI.return_value
            api.get_bot_qrcode = AsyncMock(
                side_effect=[
                    {"qrcode": "qr1"},
                    {"qrcode": "qr2"},
                ]
            )
            api.get_qrcode_status = AsyncMock(
                side_effect=[
                    {"status": "expired"},
                    {"status": "confirmed", "bot_token": "tok2", "ilink_bot_id": "b2"},
                ]
            )

            with patch("weixin_bot.auth._display_qr"):
                result = await qr_login(client)

        assert result["token"] == "tok2"
        assert api.get_bot_qrcode.call_count == 2

    @pytest.mark.asyncio
    async def test_too_many_refreshes_raises(self) -> None:
        client = WeixinClient()
        client._client = MagicMock()

        with patch("weixin_bot.auth.WeixinAPI") as MockAPI:
            api = MockAPI.return_value
            api.get_bot_qrcode = AsyncMock(return_value={"qrcode": "qr1"})
            api.get_qrcode_status = AsyncMock(return_value={"status": "expired"})

            with patch("weixin_bot.auth._display_qr"):
                with pytest.raises(AuthError, match="过期超过"):
                    await qr_login(client)

    @pytest.mark.asyncio
    async def test_redirect(self) -> None:
        client = WeixinClient()
        client._client = MagicMock()

        with patch("weixin_bot.auth.WeixinAPI") as MockAPI:
            api = MockAPI.return_value
            api.get_bot_qrcode = AsyncMock(return_value={"qrcode": "qr1"})
            api.get_qrcode_status = AsyncMock(
                side_effect=[
                    {"status": "scaned_but_redirect", "redirect_host": "ilink2.weixin.qq.com"},
                    {"status": "confirmed", "bot_token": "tok3", "ilink_bot_id": "b3"},
                ]
            )

            with patch("weixin_bot.auth._display_qr"):
                result = await qr_login(client)

        assert result["token"] == "tok3"
        # Second call should have used redirect base_url
        calls = api.get_qrcode_status.call_args_list
        assert calls[1].kwargs.get("base_url") == "https://ilink2.weixin.qq.com"
