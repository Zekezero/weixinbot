"""微信 ilink API 封装

所有 ilink 端点的高层封装。
"""

from __future__ import annotations

import logging
from typing import Any

from weixin_bot.client import (
    TIMEOUT_DEFAULT,
    TIMEOUT_GETUPDATES,
    TIMEOUT_LIGHTWEIGHT,
    TIMEOUT_QR,
    TIMEOUT_QR_POLL,
    WeixinClient,
)

logger = logging.getLogger("weixin_bot.api")


class WeixinAPI:
    """微信 ilink API 封装"""

    def __init__(self, client: WeixinClient) -> None:
        self._client = client

    def _base_info(self) -> dict[str, str]:
        return self._client._base_info()

    # ── QR 登录 ──────────────────────────────────────

    async def get_bot_qrcode(self) -> dict[str, Any]:
        """获取登录二维码"""
        return await self._client.get(
            "ilink/bot/get_bot_qrcode",
            params={"bot_type": "3"},
            timeout=TIMEOUT_QR,
            auth=False,
        )

    async def get_qrcode_status(
        self, qrcode: str, *, base_url: str | None = None
    ) -> dict[str, Any]:
        """轮询二维码扫描状态（长轮询）"""
        # 支持 IDC 重定向时切换 base_url
        if base_url:
            old_base = self._client.base_url
            self._client.base_url = base_url
            try:
                return await self._client.get(
                    "ilink/bot/get_qrcode_status",
                    params={"qrcode": qrcode},
                    timeout=TIMEOUT_QR_POLL,
                    auth=False,
                )
            finally:
                self._client.base_url = old_base
        return await self._client.get(
            "ilink/bot/get_qrcode_status",
            params={"qrcode": qrcode},
            timeout=TIMEOUT_QR_POLL,
            auth=False,
        )

    # ── 消息收发 ──────────────────────────────────────

    async def get_updates(self, get_updates_buf: str = "") -> dict[str, Any]:
        """长轮询获取新消息"""
        body: dict[str, Any] = {
            "get_updates_buf": get_updates_buf,
            "base_info": self._base_info(),
        }
        return await self._client.post(
            "ilink/bot/getupdates",
            body,
            timeout=TIMEOUT_GETUPDATES,
        )

    async def send_message(self, msg: dict[str, Any]) -> dict[str, Any]:
        """发送消息"""
        body: dict[str, Any] = {
            "msg": msg,
            "base_info": self._base_info(),
        }
        return await self._client.post(
            "ilink/bot/sendmessage",
            body,
            timeout=TIMEOUT_DEFAULT,
        )

    # ── CDN ──────────────────────────────────────────

    async def get_upload_url(
        self,
        *,
        filekey: str,
        media_type: int,
        to_user_id: str,
        rawsize: int,
        rawfilemd5: str,
        filesize: int,
        aeskey: str,
    ) -> dict[str, Any]:
        """获取 CDN 预签名上传地址"""
        body: dict[str, Any] = {
            "filekey": filekey,
            "media_type": media_type,
            "to_user_id": to_user_id,
            "rawsize": rawsize,
            "rawfilemd5": rawfilemd5,
            "filesize": filesize,
            "no_need_thumb": True,
            "aeskey": aeskey,
            "base_info": self._base_info(),
        }
        return await self._client.post(
            "ilink/bot/getuploadurl",
            body,
            timeout=TIMEOUT_DEFAULT,
        )

    # ── 配置 ──────────────────────────────────────────

    async def get_config(
        self,
        user_id: str,
        context_token: str = "",
    ) -> dict[str, Any]:
        """获取 bot 配置（typing_ticket 等）"""
        body: dict[str, Any] = {
            "ilink_user_id": user_id,
            "base_info": self._base_info(),
        }
        if context_token:
            body["context_token"] = context_token
        return await self._client.post(
            "ilink/bot/getconfig",
            body,
            timeout=TIMEOUT_LIGHTWEIGHT,
        )

    # ── Typing ───────────────────────────────────────

    async def send_typing(
        self,
        user_id: str,
        typing_ticket: str,
        status: int = 1,
    ) -> dict[str, Any]:
        """发送 Typing 指示器

        Args:
            status: 1=typing, 2=cancel
        """
        body: dict[str, Any] = {
            "ilink_user_id": user_id,
            "typing_ticket": typing_ticket,
            "status": status,
            "base_info": self._base_info(),
        }
        return await self._client.post(
            "ilink/bot/sendtyping",
            body,
            timeout=TIMEOUT_LIGHTWEIGHT,
        )
