"""weixin_bot 正式入口 — 生产机器人

内置指令 + 消息处理 + Agent 模式。

启动方式:
    weixinbot                          # console_scripts 入口
    python -m weixin_bot               # 模块直接运行
"""

from __future__ import annotations

import asyncio
import logging

from weixin_bot.bot import WeixinBot
from weixin_bot.config import WeixinBotConfig
from weixin_bot.models import IncomingEvent, WeixinMsgDTO
from weixin_bot.modes.manager import ModeManager

logger = logging.getLogger("weixin_bot.app")


def create_bot(config: WeixinBotConfig | None = None) -> WeixinBot:
    """创建并配置机器人实例

    注册所有内置指令和消息处理器。
    """
    cfg = config or WeixinBotConfig.from_env()

    # ── Agent 模式系统 ────────────────────────
    from weixin_bot.modes.events import EventBus
    from weixin_bot.modes.renderer import RendererConfig, TextRenderer

    bus = EventBus()
    mode_manager = ModeManager(bus)

    bot = WeixinBot(cfg, mode_manager=mode_manager)

    # 初始化渲染器
    renderer_config = RendererConfig(
        push_interval=cfg.renderer_push_interval,
        push_min_chars=cfg.renderer_push_min_chars,
        max_message_chars=cfg.renderer_max_message_chars,
        renderer_type=cfg.renderer_type,
    )

    async def _send_text(chat_id: str, text: str) -> None:
        await bot.send_text(chat_id, text)

    _ = TextRenderer(_send_text, bus, renderer_config)

    bot._mode_manager = mode_manager

    # ── 注册 Agent 适配器 ────────────────────────
    _register_adapters(bot, cfg, mode_manager, bus)

    _register_mode_commands(bot, mode_manager)
    _register_commands(bot)
    _register_handlers(bot)

    return bot


# ── 适配器注册 ────────────────────────────────────────


def _register_adapters(
    bot: WeixinBot,
    cfg: WeixinBotConfig,
    manager: ModeManager,
    bus: "EventBus",
) -> None:
    """注册 Agent 适配器 + 进入模式的指令"""
    from weixin_bot.modes.events import EventBus as _EB

    # OpenCode adapter
    if cfg.opencode_base_url:
        from weixin_bot.modes.adapters.opencode import OpenCodeAdapter

        oc_adapter = OpenCodeAdapter(cfg, bus)
        manager.register_adapter(oc_adapter)

        @bot.command("opencode", description="进入 OpenCode 模式")
        async def cmd_opencode(msg: WeixinMsgDTO, bot: WeixinBot) -> None:
            if manager.is_in_mode(msg.from_):
                await bot.send_text(msg.session_id, "请先 /exit 退出当前模式")
                return
            sid = await manager.enter_mode(msg.from_, "opencode")
            await bot.send_text(msg.session_id, f"已进入 OpenCode 模式 (会话 #{sid[:8]})\n发送消息直接与 Agent 对话，/exit 退出")

        @bot.command("approve", description="批准权限请求")
        async def cmd_approve(msg: WeixinMsgDTO, bot: WeixinBot) -> None:
            result = await oc_adapter.approve(msg.from_)
            await bot.send_text(msg.session_id, result)

        @bot.command("reject", description="拒绝权限请求")
        async def cmd_reject(msg: WeixinMsgDTO, bot: WeixinBot) -> None:
            result = await oc_adapter.reject(msg.from_)
            await bot.send_text(msg.session_id, result)

        @bot.command("abort", description="中止当前任务")
        async def cmd_abort(msg: WeixinMsgDTO, bot: WeixinBot) -> None:
            result = await oc_adapter.abort(msg.from_)
            await bot.send_text(msg.session_id, result)

    # Hermes adapter
    if cfg.hermes_base_url and cfg.hermes_api_key:
        from weixin_bot.modes.adapters.hermes import HermesAdapter

        hermes_adapter = HermesAdapter(cfg, bus)
        manager.register_adapter(hermes_adapter)

        @bot.command("hermes", description="进入 Hermes 模式")
        async def cmd_hermes(msg: WeixinMsgDTO, bot: WeixinBot) -> None:
            if manager.is_in_mode(msg.from_):
                await bot.send_text(msg.session_id, "请先 /exit 退出当前模式")
                return
            sid = await manager.enter_mode(msg.from_, "hermes")
            await bot.send_text(msg.session_id, f"已进入 Hermes 模式 (会话 #{sid[:8]})\n发送消息直接与 Agent 对话，/exit 退出")


# ── 指令注册 ──────────────────────────────────────────


def _register_commands(bot: WeixinBot) -> None:
    """注册内置指令"""

    @bot.command("ping", description="测试连通性")
    async def cmd_ping(msg: WeixinMsgDTO, bot: WeixinBot) -> None:
        await bot.send_text(msg.session_id, "pong!")

    @bot.command("echo", description="回声测试")
    async def cmd_echo(msg: WeixinMsgDTO, bot: WeixinBot) -> None:
        parts = msg.text.strip().split(maxsplit=1)
        text = parts[1] if len(parts) > 1 else "(空)"
        await bot.send_text(msg.session_id, text)


def _register_mode_commands(bot: WeixinBot, manager: ModeManager) -> None:
    """注册模式相关指令"""

    @bot.command("exit", description="退出当前模式")
    async def cmd_exit(msg: WeixinMsgDTO, bot: WeixinBot) -> None:
        if not manager.is_in_mode(msg.from_):
            await bot.send_text(msg.session_id, "当前不在任何模式中")
            return
        state = manager.get_user_mode(msg.from_)
        mode_name = state.mode_name if state else "未知"
        try:
            await manager.exit_mode(msg.from_)
        except Exception as exc:
            logger.debug("exit_mode 清理时忽略错误: %s", exc)
        await bot.send_text(msg.session_id, f"已退出 {mode_name} 模式")

    @bot.command("new", description="当前模式下新建会话")
    async def cmd_new(msg: WeixinMsgDTO, bot: WeixinBot) -> None:
        if not manager.is_in_mode(msg.from_):
            await bot.send_text(msg.session_id, "当前不在任何模式中")
            return
        sid = await manager.new_session(msg.from_)
        await bot.send_text(msg.session_id, f"新会话已创建: #{sid[:8]}")

    @bot.command("modes", description="列出可用模式")
    async def cmd_modes(msg: WeixinMsgDTO, bot: WeixinBot) -> None:
        lines = ["可用模式:"]
        for name, adapter in manager._adapters.items():
            lines.append(f"  /{name} - {adapter.display_name}")
        await bot.send_text(msg.session_id, "\n".join(lines))


# ── 消息处理 ──────────────────────────────────────────


def _register_handlers(bot: WeixinBot) -> None:
    """注册消息/事件处理器"""

    @bot.on_message()
    async def handle_message(event: IncomingEvent) -> None:
        msg = event.as_message()
        await bot.reply(event, f"收到: {msg.text}\n\n发 /help 查看指令")


# ── 主入口 ────────────────────────────────────────────


def main() -> None:
    """启动机器人"""
    from weixin_bot.util.logger import setup_logging

    setup_logging()

    bot = create_bot()
    bot.run()


if __name__ == "__main__":
    main()
