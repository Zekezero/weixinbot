"""最简回声 bot — 3 行核心代码"""

from weixin_bot.bot import WeixinBot
from weixin_bot.config import WeixinBotConfig
from weixin_bot.models import IncomingEvent

bot = WeixinBot(WeixinBotConfig.from_env())


@bot.on_message()
async def echo(event: IncomingEvent) -> None:
    msg = event.as_message()
    await bot.reply(event, f"你说: {msg.text}")


if __name__ == "__main__":
    bot.run()
