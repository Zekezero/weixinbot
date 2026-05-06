"""WeixinBot 主类 — 一站式机器人入口"""

from __future__ import annotations

import asyncio
import logging
import signal
from pathlib import Path
from typing import Any, Awaitable, Callable

from weixin_bot.api import WeixinAPI
from weixin_bot.auth import is_logged_in, load_account, qr_login, save_account
from weixin_bot.client import WeixinClient
from weixin_bot.commands import BotLike, CommandRouter
from weixin_bot.config import WeixinBotConfig
from weixin_bot.handler import HandlerRegistry
from weixin_bot.messaging import build_text_message, extract_media_items, extract_text
from weixin_bot.models import EventType, IncomingEvent, WeixinMessage, WeixinMsgDTO
from weixin_bot.monitor import WeixinMonitor
from weixin_bot.modes.manager import ModeManager

logger = logging.getLogger("weixin_bot.bot")


class WeixinBot:
    """微信机器人 — 一站式入口

    组装 WeixinClient + CommandRouter + HandlerRegistry + ModeManager + WeixinMonitor。
    """

    def __init__(
        self,
        config: WeixinBotConfig,
        mode_manager: ModeManager | None = None,
    ) -> None:
        self.config = config
        self._client = WeixinClient()
        self._api = WeixinAPI(self._client)
        self._command_router = CommandRouter()
        self._handler_registry = HandlerRegistry()
        self._mode_manager = mode_manager
        self._monitor: WeixinMonitor | None = None
        self._running = False
        self._stop_event = asyncio.Event()

        # 注册内置 /help
        self._register_help()

    # ── 装饰器 API ────────────────────────────────────

    def command(
        self,
        name: str,
        *,
        description: str = "",
        p2p_only: bool = False,
        group_only: bool = False,
        aliases: list[str] | None = None,
    ) -> Callable[..., Any]:
        """注册指令"""
        return self._command_router.command(
            name, description=description, p2p_only=p2p_only, group_only=group_only, aliases=aliases,
        )

    def on_message(
        self,
        *,
        msg_types: list[int] | None = None,
        p2p_only: bool = False,
        group_only: bool = False,
    ) -> Callable[..., Any]:
        """注册消息处理器"""
        return self._handler_registry.on_message(
            msg_types=msg_types, p2p_only=p2p_only, group_only=group_only,
        )

    def on_recall(self) -> Callable[..., Any]:
        """注册撤回处理器"""
        return self._handler_registry.on_recall()

    # ── 消息发送 ────────────────────────────────────

    async def send_text(self, receiver: str, content: str) -> None:
        """发送文本消息"""
        assert self._monitor is not None, "Bot 未启动"
        ctx_token = self._monitor.get_context_token(receiver)
        msg = build_text_message(receiver, content, ctx_token)
        await self._api.send_message(msg)

    async def reply(self, event: IncomingEvent, content: str) -> None:
        """回复消息"""
        msg = event.as_message()
        await self.send_text(msg.session_id, content)

    # ── 生命周期 ────────────────────────────────────

    async def start(self) -> None:
        """异步启动（非阻塞）"""
        state_dir = self.config.resolved_state_dir
        state_dir.mkdir(parents=True, exist_ok=True)

        await self._client.start()

        # 登录
        await self._ensure_login(state_dir)

        # 创建 Monitor
        self._monitor = WeixinMonitor(
            client=self._client,
            state_dir=state_dir,
            on_message=self._dispatch_raw,
        )

        self._running = True
        self._stop_event.clear()

        # 启动消息循环（后台任务）
        asyncio.create_task(self._run_monitor())
        logger.info("WeixinBot 已启动")

    async def stop(self) -> None:
        """停止机器人"""
        self._running = False
        if self._monitor:
            self._monitor.stop()
        await self._client.close()
        self._stop_event.set()
        logger.info("WeixinBot 已停止")

    async def wait(self) -> None:
        """等待机器人停止"""
        await self._stop_event.wait()

    def run(self) -> None:
        """阻塞式启动（同步入口）"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def _main() -> None:
            await self.start()

            # 信号处理
            for sig in (signal.SIGINT, signal.SIGTERM):
                try:
                    loop.add_signal_handler(sig, lambda: asyncio.create_task(self.stop()))
                except NotImplementedError:
                    # Windows 不支持 add_signal_handler
                    pass

            await self.wait()

        try:
            loop.run_until_complete(_main())
        except KeyboardInterrupt:
            loop.run_until_complete(self.stop())
        finally:
            loop.close()

    # ── 登录 ────────────────────────────────────────

    async def _ensure_login(self, state_dir: Path) -> None:
        """确保已登录，未登录则触发 QR 扫码"""
        # 尝试加载已有凭证
        accounts = self._list_account_ids(state_dir)
        for account_id in accounts:
            creds = load_account(state_dir, account_id)
            if creds and creds.get("token"):
                self._client.token = creds["token"]
                self._client.base_url = creds.get("baseUrl", self._client.base_url)
                self._client.account_id = account_id
                logger.info("已加载凭证: %s", account_id)
                return

        # 需要 QR 登录
        logger.info("未找到有效凭证，启动 QR 扫码登录...")
        result = await qr_login(self._client)
        self._client.token = result["token"]
        self._client.base_url = result.get("baseUrl", self._client.base_url)
        self._client.account_id = result["accountId"]

        save_account(
            state_dir,
            result["accountId"],
            result["token"],
            result.get("baseUrl", ""),
            result.get("userId", ""),
        )

    def _list_account_ids(self, state_dir: Path) -> list[str]:
        """列出已保存的账号 ID"""
        index_file = state_dir / "accounts.json"
        if not index_file.exists():
            return []
        import json

        try:
            return json.loads(index_file.read_text(encoding="utf-8"))
        except Exception:
            return []

    # ── 消息分发 ────────────────────────────────────

    async def _run_monitor(self) -> None:
        """运行消息循环"""
        assert self._monitor is not None
        try:
            await self._monitor.start()
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("消息循环异常退出")
        finally:
            self._stop_event.set()

    async def _dispatch_raw(self, raw_msg: dict[str, Any]) -> None:
        """分发原始消息"""
        # 跳过 bot 自己的消息
        msg_type = raw_msg.get("message_type", 0)
        if msg_type == 2:  # BOT
            return

        from_user_id = raw_msg.get("from_user_id", "")
        if not from_user_id:
            return

        # 启动 Typing
        if self._monitor:
            await self._monitor.start_typing(from_user_id)

        try:
            # 构建 IncomingEvent
            weixin_msg = WeixinMessage.model_validate(raw_msg)
            event = IncomingEvent(raw=weixin_msg)

            await self._dispatch(event)
        finally:
            # 停止 Typing
            if self._monitor:
                await self._monitor.stop_typing(from_user_id)

    async def _dispatch(self, event: IncomingEvent) -> None:
        """事件分发管道: 白名单 → 指令 → 模式 → 处理器"""
        msg = event.as_message()

        # 1. 白名单检查
        if self.config.allowed_users and msg.from_ not in self.config.allowed_users:
            logger.debug("用户不在白名单: %s", msg.from_)
            return

        # 2. 指令路由
        if await self._command_router.try_handle(msg, self):
            return

        # 3. 模式转发
        if self._mode_manager and await self._mode_manager.try_forward(event):
            return

        # 4. 事件处理器
        await self._handler_registry.dispatch(event)

    # ── 内置指令 ────────────────────────────────────

    def _register_help(self) -> None:
        @self._command_router.command("help", description="显示帮助")
        async def cmd_help(msg: WeixinMsgDTO, bot: BotLike) -> None:
            await bot.send_text(msg.session_id, self._command_router.help_text())

        @self._command_router.command("health", description="健康检查")
        async def cmd_health(msg: WeixinMsgDTO, bot: BotLike) -> None:
            lines = [
                f"登录状态: {'已登录' if self._client.token else '未登录'}",
                f"账号: {self._client.account_id or '未知'}",
                f"消息循环: {'运行中' if self._running else '已停止'}",
            ]
            if self._mode_manager:
                active = len(self._mode_manager._user_modes)
                lines.append(f"活跃模式会话: {active}")
            await bot.send_text(msg.session_id, "\n".join(lines))
