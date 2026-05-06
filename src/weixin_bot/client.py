"""微信 ilink HTTP 客户端

封装 httpx.AsyncClient，注入标准请求头、超时管理、base_info。
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from weixin_bot import __version__
from weixin_bot.util.random import generate_wechat_uin

logger = logging.getLogger("weixin_bot.client")

DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com"
CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"

# 超时配置（秒）
TIMEOUT_GETUPDATES = 45  # 长轮询 35s + 10s 网络余量
TIMEOUT_DEFAULT = 15
TIMEOUT_LIGHTWEIGHT = 10
TIMEOUT_QR = 5
TIMEOUT_QR_POLL = 45  # 长轮询 35s + 10s


class WeixinClient:
    """微信 ilink HTTP 客户端"""

    def __init__(
        self,
        token: str = "",
        base_url: str = DEFAULT_BASE_URL,
        account_id: str = "",
    ) -> None:
        self._token = token
        self._base_url = base_url.rstrip("/")
        self._account_id = account_id
        self._client: httpx.AsyncClient | None = None

    @property
    def token(self) -> str:
        return self._token

    @token.setter
    def token(self, value: str) -> None:
        self._token = value

    @property
    def base_url(self) -> str:
        return self._base_url

    @base_url.setter
    def base_url(self, value: str) -> None:
        self._base_url = value.rstrip("/")

    @property
    def account_id(self) -> str:
        return self._account_id

    @account_id.setter
    def account_id(self, value: str) -> None:
        self._account_id = value

    async def start(self) -> None:
        """初始化 HTTP 客户端"""
        if self._client is not None:
            return
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(TIMEOUT_DEFAULT, connect=10),
            follow_redirects=True,
        )

    async def close(self) -> None:
        """关闭 HTTP 客户端"""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _build_headers(self, *, auth: bool = True) -> dict[str, str]:
        """构建标准请求头"""
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "AuthorizationType": "ilink_bot_token",
            "X-WECHAT-UIN": generate_wechat_uin(),
        }
        if auth and self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _base_info(self) -> dict[str, str]:
        """构建 base_info 字段"""
        return {"channel_version": __version__}

    async def post(
        self,
        path: str,
        body: dict[str, Any],
        *,
        timeout: float = TIMEOUT_DEFAULT,
        auth: bool = True,
    ) -> dict[str, Any]:
        """POST 请求到 ilink API"""
        assert self._client is not None, "Client not started. Call start() first."
        url = f"{self._base_url}/{path}"
        headers = self._build_headers(auth=auth)

        resp = await self._client.post(
            url,
            json=body,
            headers=headers,
            timeout=httpx.Timeout(timeout, connect=10),
        )
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    async def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: float = TIMEOUT_DEFAULT,
        auth: bool = True,
    ) -> dict[str, Any]:
        """GET 请求到 ilink API"""
        assert self._client is not None, "Client not started. Call start() first."
        url = f"{self._base_url}/{path}"
        headers = self._build_headers(auth=auth)

        resp = await self._client.get(
            url,
            params=params,
            headers=headers,
            timeout=httpx.Timeout(timeout, connect=10),
        )
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    async def post_binary(
        self,
        url: str,
        data: bytes,
        *,
        timeout: float = TIMEOUT_DEFAULT,
    ) -> httpx.Response:
        """POST 二进制数据（CDN 上传）"""
        assert self._client is not None, "Client not started. Call start() first."
        resp = await self._client.post(
            url,
            content=data,
            headers={"Content-Type": "application/octet-stream"},
            timeout=httpx.Timeout(timeout, connect=10),
        )
        resp.raise_for_status()
        return resp

    async def get_binary(
        self,
        url: str,
        *,
        timeout: float = TIMEOUT_DEFAULT,
    ) -> bytes:
        """GET 二进制数据（CDN 下载）"""
        assert self._client is not None, "Client not started. Call start() first."
        resp = await self._client.get(
            url,
            timeout=httpx.Timeout(timeout, connect=10),
        )
        resp.raise_for_status()
        return resp.content
