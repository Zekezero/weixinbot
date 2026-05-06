"""长轮询消息循环

通过 getUpdates 长轮询持续接收消息，支持断点续传、重试退避、会话过期处理。
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Awaitable

from weixin_bot.api import WeixinAPI
from weixin_bot.client import WeixinClient
from weixin_bot.errors import SessionExpiredError

logger = logging.getLogger("weixin_bot.monitor")

# 重试参数（对齐 nanobot/weixin-agent-sdk）
MAX_CONSECUTIVE_FAILURES = 3
BACKOFF_DELAY_S = 30
RETRY_DELAY_S = 2
SESSION_PAUSE_DURATION_S = 3600  # 1 小时
TYPING_KEEPALIVE_INTERVAL_S = 10

# 消息去重
DEDUPE_CACHE_CAPACITY = 10000


class WeixinMonitor:
    """长轮询消息循环"""

    def __init__(
        self,
        client: WeixinClient,
        state_dir: Path,
        on_message: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        self._client = client
        self._api = WeixinAPI(client)
        self._state_dir = state_dir
        self._on_message = on_message

        self._running = False
        self._get_updates_buf = ""
        self._next_poll_timeout_ms = 35000
        self._consecutive_failures = 0
        self._session_pause_until: float = 0

        # 消息去重 LRU 缓存
        self._seen_msg_ids: OrderedDict[str, float] = OrderedDict()

        # context_token 缓存: "accountId:userId" → token
        self._context_tokens: dict[str, str] = {}

        # typing 状态
        self._typing_tasks: dict[str, asyncio.Task[None]] = {}
        self._typing_tickets: dict[str, tuple[str, float]] = {}  # userId → (ticket, fetched_at)

    @property
    def context_tokens(self) -> dict[str, str]:
        return self._context_tokens

    def get_context_token(self, user_id: str) -> str:
        """获取用户的 context_token"""
        key = f"{self._client.account_id}:{user_id}"
        return self._context_tokens.get(key, "")

    def set_context_token(self, user_id: str, token: str) -> None:
        """缓存用户的 context_token"""
        key = f"{self._client.account_id}:{user_id}"
        self._context_tokens[key] = token

    # ── 生命周期 ────────────────────────────────────

    async def start(self) -> None:
        """启动长轮询循环"""
        self._running = True
        self._load_sync_buf()
        logger.info("消息循环已启动")

        while self._running:
            # 会话暂停检查
            if self._session_pause_until > 0:
                remaining = self._session_pause_until - time.time()
                if remaining > 0:
                    logger.debug("会话暂停中，剩余 %.0f 秒", remaining)
                    await asyncio.sleep(min(remaining, 30))
                    continue
                else:
                    self._session_pause_until = 0
                    logger.info("会话暂停结束，恢复轮询")

            try:
                await self._poll_once()
            except asyncio.CancelledError:
                break
            except SessionExpiredError:
                self._pause_session()
            except Exception as exc:
                self._consecutive_failures += 1
                logger.error("轮询错误 (%d 次): %s", self._consecutive_failures, exc)
                if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    logger.warning("连续 %d 次失败，退避 %ds", MAX_CONSECUTIVE_FAILURES, BACKOFF_DELAY_S)
                    await asyncio.sleep(BACKOFF_DELAY_S)
                    self._consecutive_failures = 0
                else:
                    await asyncio.sleep(RETRY_DELAY_S)

    def stop(self) -> None:
        """停止长轮询循环"""
        self._running = False
        # 取消所有 typing 任务
        for task in self._typing_tasks.values():
            task.cancel()
        self._typing_tasks.clear()

    # ── 单次轮询 ────────────────────────────────────

    async def _poll_once(self) -> None:
        """执行一次 getUpdates"""
        try:
            data = await self._api.get_updates(self._get_updates_buf)
        except asyncio.TimeoutError:
            # 客户端超时是正常的长轮询行为
            logger.debug("getUpdates 超时（正常）")
            return

        ret = data.get("ret", 0)
        errcode = data.get("errcode", 0)

        # 会话过期
        if errcode == -14 or ret == -14:
            raise SessionExpiredError(
                f"会话过期 (errcode={errcode}, ret={ret})",
                ret=ret,
                errcode=errcode,
                errmsg=data.get("errmsg", ""),
            )

        # API 错误
        if ret != 0 or (errcode != 0 and errcode != -14):
            self._consecutive_failures += 1
            errmsg = data.get("errmsg", "")
            logger.warning("getUpdates 错误: ret=%s, errcode=%s, errmsg=%s", ret, errcode, errmsg)
            if self._consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                await asyncio.sleep(BACKOFF_DELAY_S)
                self._consecutive_failures = 0
            else:
                await asyncio.sleep(RETRY_DELAY_S)
            return

        # 成功
        self._consecutive_failures = 0

        # 服务端建议超时
        server_timeout = data.get("longpolling_timeout_ms")
        if server_timeout and server_timeout > 0:
            self._next_poll_timeout_ms = max(server_timeout, 5000)

        # 保存 sync buffer
        new_buf = data.get("get_updates_buf", "")
        if new_buf:
            self._get_updates_buf = new_buf
            self._save_sync_buf()

        # 处理消息
        msgs = data.get("msgs") or []
        for msg in msgs:
            await self._handle_message(msg)

    async def _handle_message(self, msg: dict[str, Any]) -> None:
        """处理单条消息"""
        # 消息去重
        msg_id = str(msg.get("message_id", "")) or str(msg.get("seq", ""))
        if self._is_duplicate(msg_id):
            logger.debug("跳过重复消息: %s", msg_id)
            return

        # 缓存 context_token
        ctx_token = msg.get("context_token", "")
        from_user_id = msg.get("from_user_id", "")
        if ctx_token and from_user_id:
            self.set_context_token(from_user_id, ctx_token)

        # 分发到回调
        try:
            await self._on_message(msg)
        except Exception as exc:
            logger.error("处理消息失败: %s", exc, exc_info=True)

    # ── 消息去重 ────────────────────────────────────

    def _is_duplicate(self, msg_id: str) -> bool:
        """LRU 缓存检查消息是否重复（容量 10000，TTL 30 分钟）"""
        if not msg_id:
            return False

        now = time.time()

        # 检查是否已存在
        if msg_id in self._seen_msg_ids:
            ts = self._seen_msg_ids[msg_id]
            if now - ts < 1800:  # 30 分钟 TTL
                return True
            # 过期，移除
            del self._seen_msg_ids[msg_id]

        # 清理过期条目
        while self._seen_msg_ids:
            oldest_id, oldest_ts = next(iter(self._seen_msg_ids.items()))
            if now - oldest_ts > 1800:
                del self._seen_msg_ids[oldest_id]
            else:
                break

        # 容量限制
        while len(self._seen_msg_ids) >= DEDUPE_CACHE_CAPACITY:
            self._seen_msg_ids.popitem(last=False)

        # 加入缓存
        self._seen_msg_ids[msg_id] = now
        return False

    # ── 会话暂停 ────────────────────────────────────

    def _pause_session(self) -> None:
        """暂停会话 1 小时（errcode=-14 触发）"""
        self._session_pause_until = time.time() + SESSION_PAUSE_DURATION_S
        logger.warning(
            "会话过期 (errcode=-14)，暂停 %d 分钟。请重新登录。",
            SESSION_PAUSE_DURATION_S // 60,
        )

    # ── Typing 指示器 ────────────────────────────────

    async def start_typing(self, user_id: str) -> None:
        """开始 Typing 指示器（自动 10s 刷新）"""
        # 取消旧任务
        await self.stop_typing(user_id)

        ticket = await self._get_typing_ticket(user_id)
        if not ticket:
            return

        async def _keepalive() -> None:
            try:
                await self._api.send_typing(user_id, ticket, status=1)
                while True:
                    await asyncio.sleep(TYPING_KEEPALIVE_INTERVAL_S)
                    try:
                        await self._api.send_typing(user_id, ticket, status=1)
                    except Exception:
                        pass  # best-effort
            except asyncio.CancelledError:
                pass

        self._typing_tasks[user_id] = asyncio.create_task(_keepalive())

    async def stop_typing(self, user_id: str) -> None:
        """停止 Typing 指示器"""
        task = self._typing_tasks.pop(user_id, None)
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # 发送取消
        ticket = await self._get_typing_ticket(user_id)
        if ticket:
            try:
                await self._api.send_typing(user_id, ticket, status=2)
            except Exception:
                pass  # best-effort

    async def _get_typing_ticket(self, user_id: str) -> str:
        """获取 typing_ticket（带缓存，24h TTL）"""
        now = time.time()
        cached = self._typing_tickets.get(user_id)
        if cached:
            ticket, fetched_at = cached
            if now - fetched_at < 86400:  # 24h
                return ticket

        try:
            ctx_token = self.get_context_token(user_id)
            resp = await self._api.get_config(user_id, ctx_token)
            ticket = resp.get("typing_ticket", "")
            if ticket:
                self._typing_tickets[user_id] = (ticket, now)
                return ticket
        except Exception as exc:
            logger.debug("获取 typing_ticket 失败: %s", exc)

        return ""

    # ── Sync Buffer 持久化 ──────────────────────────

    def _sync_buf_path(self) -> Path:
        sync_dir = self._state_dir / "sync"
        sync_dir.mkdir(parents=True, exist_ok=True)
        account_id = self._client.account_id or "default"
        safe_id = account_id.strip().lower().replace("@", "-").replace(".", "-")
        return sync_dir / f"{safe_id}.buf"

    def _load_sync_buf(self) -> None:
        path = self._sync_buf_path()
        if path.exists():
            try:
                self._get_updates_buf = path.read_text(encoding="utf-8").strip()
                logger.info("已加载 sync buffer: %s", path)
            except OSError as exc:
                logger.warning("加载 sync buffer 失败: %s", exc)

    def _save_sync_buf(self) -> None:
        path = self._sync_buf_path()
        try:
            path.write_text(self._get_updates_buf, encoding="utf-8")
        except OSError as exc:
            logger.warning("保存 sync buffer 失败: %s", exc)
