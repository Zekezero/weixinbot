"""指令路由器 — /xxx 命令注册与分发"""

from __future__ import annotations

import logging
from typing import Awaitable, Callable, Protocol

from weixin_bot.models import WeixinMsgDTO

logger = logging.getLogger("weixin_bot.commands")

CommandHandler = Callable[..., Awaitable[None]]


class BotLike(Protocol):
    async def send_text(
        self,
        receiver: str,
        content: str,
    ) -> None:
        ...


class CommandRouter:
    """指令路由器

    将 /xxx 格式的文本消息分发到对应处理函数。
    """

    def __init__(self, prefix: str = "/") -> None:
        self.prefix = prefix
        self._commands: dict[str, _CommandEntry] = {}

    def command(
        self,
        name: str,
        *,
        description: str = "",
        p2p_only: bool = False,
        group_only: bool = False,
        aliases: list[str] | None = None,
    ) -> Callable[[CommandHandler], CommandHandler]:
        """注册一个指令"""
        def decorator(fn: CommandHandler) -> CommandHandler:
            entry = _CommandEntry(
                name=name,
                handler=fn,
                description=description,
                p2p_only=p2p_only,
                group_only=group_only,
            )
            self._commands[name] = entry
            for alias in (aliases or []):
                self._commands[alias] = entry
            logger.debug("注册指令: %s%s -> %s", self.prefix, name, fn.__name__)
            return fn
        return decorator

    async def try_handle(self, msg: WeixinMsgDTO, bot: BotLike) -> bool:
        """尝试匹配并执行指令

        Returns:
            True 如果匹配到了指令, False 否则
        """
        text = msg.text.strip()
        if not text.startswith(self.prefix):
            return False

        parts = text[len(self.prefix):].split(maxsplit=1)
        if not parts:
            return False

        cmd_name = parts[0].lower()
        entry = self._commands.get(cmd_name)
        if entry is None:
            return False

        # 检查场景限制
        if entry.p2p_only and not msg.is_p2p:
            await bot.send_text(msg.session_id, f"{self.prefix}{cmd_name} 仅支持私聊")
            return True

        if entry.group_only and not msg.is_group:
            await bot.send_text(msg.session_id, "此指令仅支持群聊，微信当前不支持群聊功能")
            return True

        logger.info("执行指令: %s%s (来自 %s)", self.prefix, cmd_name, msg.from_)
        await entry.handler(msg, bot)
        return True

    def help_text(self) -> str:
        """生成帮助文本"""
        seen: set[str] = set()
        lines = ["可用指令:"]
        for name, entry in self._commands.items():
            if entry.name in seen:
                continue
            seen.add(entry.name)
            scope = ""
            if entry.p2p_only:
                scope = " [仅私聊]"
            elif entry.group_only:
                scope = " [仅群聊]"
            desc = f" - {entry.description}" if entry.description else ""
            lines.append(f"  {self.prefix}{entry.name}{desc}{scope}")
        return "\n".join(lines)

    @property
    def registered_commands(self) -> list[str]:
        return list({e.name for e in self._commands.values()})


class _CommandEntry:
    __slots__ = ("name", "handler", "description", "p2p_only", "group_only")

    def __init__(
        self,
        name: str,
        handler: CommandHandler,
        description: str,
        p2p_only: bool,
        group_only: bool,
    ) -> None:
        self.name = name
        self.handler = handler
        self.description = description
        self.p2p_only = p2p_only
        self.group_only = group_only
