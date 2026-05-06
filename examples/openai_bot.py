"""OpenAI Agent 对接示例 — 多轮对话 + Vision"""

from __future__ import annotations

import base64
import os
from pathlib import Path

from weixin_bot.bot import WeixinBot
from weixin_bot.config import WeixinBotConfig
from weixin_bot.models import IncomingEvent

# 对话历史 per-user
_histories: dict[str, list[dict[str, object]]] = {}

bot = WeixinBot(WeixinBotConfig.from_env())


@bot.command("clear", description="清空对话历史")
async def cmd_clear(msg: object, bot: WeixinBot) -> None:
    from weixin_bot.models import WeixinMsgDTO

    m = msg if isinstance(msg, WeixinMsgDTO) else None
    if m:
        _histories.pop(m.from_, None)
        await bot.send_text(m.session_id, "对话历史已清空")


@bot.on_message()
async def chat(event: IncomingEvent) -> None:
    msg = event.as_message()
    user_id = msg.from_

    # 初始化 OpenAI 客户端
    try:
        from openai import AsyncOpenAI
    except ImportError:
        await bot.reply(event, "需要安装 openai: pip install openai")
        return

    client = AsyncOpenAI(
        api_key=os.environ.get("OPENAI_API_KEY", ""),
        base_url=os.environ.get("OPENAI_BASE_URL"),
    )
    model = os.environ.get("OPENAI_MODEL", "gpt-4o")

    # 构建消息
    history = _histories.setdefault(user_id, [])
    content: list[dict[str, object]] = [{"type": "text", "text": msg.text}]

    # 处理图片 (Vision)
    for media in msg.media_list:
        if media.type.value == 2 and media.local_path:  # IMAGE
            try:
                img_data = Path(media.local_path).read_bytes()
                b64 = base64.b64encode(img_data).decode()
                mime = media.mime_type or "image/jpeg"
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}"},
                })
            except Exception:
                pass

    history.append({"role": "user", "content": content})

    # 调用 OpenAI
    system_prompt = os.environ.get("OPENAI_SYSTEM_PROMPT", "你是一个有帮助的助手。")
    messages = [{"role": "system", "content": system_prompt}] + history[-20:]  # 保留最近 20 轮

    try:
        resp = await client.chat.completions.create(model=model, messages=messages)
        reply_text = resp.choices[0].message.content or "(空回复)"
    except Exception as exc:
        reply_text = f"调用失败: {exc}"

    history.append({"role": "assistant", "content": reply_text})

    # 限制历史长度
    if len(history) > 40:
        history[:] = history[-40:]

    await bot.reply(event, reply_text)


if __name__ == "__main__":
    bot.run()
