"""19.6 测试 CommandRouter 指令匹配与分发"""

import pytest

from weixin_bot.commands import CommandRouter
from weixin_bot.models import WeixinMsgDTO


def _make_msg(text: str = "", from_: str = "user1", is_p2p: bool = True) -> WeixinMsgDTO:
    return WeixinMsgDTO(
        from_=from_,
        session_id=from_,
        text=text,
        is_p2p=is_p2p,
        is_group=not is_p2p,
        media_list=[],
    )


class _FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    async def send_text(self, receiver: str, content: str) -> None:
        self.sent.append((receiver, content))


class TestCommandRouter:
    @pytest.fixture
    def router(self) -> CommandRouter:
        r = CommandRouter()

        @r.command("ping", description="测试")
        async def cmd_ping(msg: WeixinMsgDTO, bot: _FakeBot) -> None:
            await bot.send_text(msg.session_id, "pong!")

        @r.command("greet", description="问候", aliases=["hi"])
        async def cmd_greet(msg: WeixinMsgDTO, bot: _FakeBot) -> None:
            await bot.send_text(msg.session_id, f"你好 {msg.from_}")

        @r.command("admin", description="管理", p2p_only=True)
        async def cmd_admin(msg: WeixinMsgDTO, bot: _FakeBot) -> None:
            await bot.send_text(msg.session_id, "admin ok")

        return r

    @pytest.mark.asyncio
    async def test_match_command(self, router: CommandRouter) -> None:
        bot = _FakeBot()
        msg = _make_msg("/ping")
        assert await router.try_handle(msg, bot) is True
        assert bot.sent == [("user1", "pong!")]

    @pytest.mark.asyncio
    async def test_no_match(self, router: CommandRouter) -> None:
        bot = _FakeBot()
        msg = _make_msg("hello world")
        assert await router.try_handle(msg, bot) is False
        assert bot.sent == []

    @pytest.mark.asyncio
    async def test_unknown_command(self, router: CommandRouter) -> None:
        bot = _FakeBot()
        msg = _make_msg("/unknown")
        assert await router.try_handle(msg, bot) is False

    @pytest.mark.asyncio
    async def test_alias(self, router: CommandRouter) -> None:
        bot = _FakeBot()
        msg = _make_msg("/hi")
        assert await router.try_handle(msg, bot) is True
        assert bot.sent == [("user1", "你好 user1")]

    @pytest.mark.asyncio
    async def test_case_insensitive(self, router: CommandRouter) -> None:
        bot = _FakeBot()
        msg = _make_msg("/PING")
        assert await router.try_handle(msg, bot) is True

    @pytest.mark.asyncio
    async def test_p2p_only_in_group(self, router: CommandRouter) -> None:
        bot = _FakeBot()
        msg = _make_msg("/admin", is_p2p=False)
        assert await router.try_handle(msg, bot) is True
        assert "仅支持私聊" in bot.sent[0][1]

    @pytest.mark.asyncio
    async def test_p2p_only_in_p2p(self, router: CommandRouter) -> None:
        bot = _FakeBot()
        msg = _make_msg("/admin", is_p2p=True)
        assert await router.try_handle(msg, bot) is True
        assert bot.sent == [("user1", "admin ok")]

    def test_help_text(self, router: CommandRouter) -> None:
        text = router.help_text()
        assert "/ping" in text
        assert "/greet" in text
        assert "测试" in text

    def test_registered_commands(self, router: CommandRouter) -> None:
        names = router.registered_commands
        assert "ping" in names
        assert "greet" in names
