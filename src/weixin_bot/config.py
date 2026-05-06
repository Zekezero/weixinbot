"""weixin_bot 配置管理

从 .env 文件和环境变量加载配置。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _env_bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key, "").lower()
    if not val:
        return default
    return val in ("1", "true", "yes", "on")


def _env_float(key: str, default: float) -> float:
    val = os.environ.get(key, "")
    if not val:
        return default
    try:
        return float(val)
    except ValueError:
        return default


def _env_int(key: str, default: int) -> int:
    val = os.environ.get(key, "")
    if not val:
        return default
    try:
        return int(val)
    except ValueError:
        return default


@dataclass(frozen=True)
class WeixinBotConfig:
    """机器人主配置"""

    # ── 微信 ilink ──
    state_dir: str = ""
    log_level: str = "INFO"

    # ── Hermes Agent ──
    hermes_api_key: str = ""
    hermes_base_url: str = ""

    # ── OpenCode Agent ──
    opencode_base_url: str = "http://localhost:29107"
    opencode_project_dir: str = ""

    # ── 渲染器 ──
    renderer_type: str = "text"
    renderer_push_interval: float = 3.0
    renderer_push_min_chars: int = 2000
    renderer_max_message_chars: int = 3000

    # ── 流式卡片（预留） ──
    streaming_card_enabled: bool = False
    streaming_card_template_uuid: str = ""
    streaming_card_max_chars: int = 8000
    streaming_card_push_interval: float = 0.5
    streaming_card_push_min_chars: int = 20

    # ── 用户白名单（空表示不限制） ──
    allowed_users: list[str] = field(default_factory=list)

    @classmethod
    def from_env(cls, dotenv_path: str | Path | None = None) -> WeixinBotConfig:
        """从 .env 文件和环境变量加载配置"""
        # 尝试加载 .env
        try:
            from dotenv import load_dotenv

            load_dotenv(dotenv_path or ".env", override=False)
        except ImportError:
            pass

        allowed_raw = _env("WEIXIN_ALLOWED_USERS", "")
        allowed = [u.strip() for u in allowed_raw.split(",") if u.strip()] if allowed_raw else []

        return cls(
            state_dir=_env("WEIXIN_STATE_DIR", ""),
            log_level=_env("WEIXIN_LOG_LEVEL", "INFO"),
            hermes_api_key=_env("HERMES_API_KEY", ""),
            hermes_base_url=_env("HERMES_BASE_URL", ""),
            opencode_base_url=_env("OPENCODE_BASE_URL", "http://localhost:29107"),
            opencode_project_dir=_env("OPENCODE_PROJECT_DIR", ""),
            renderer_type=_env("WEIXIN_RENDERER_TYPE", "text"),
            renderer_push_interval=_env_float("WEIXIN_RENDERER_PUSH_INTERVAL", 3.0),
            renderer_push_min_chars=_env_int("WEIXIN_RENDERER_PUSH_MIN_CHARS", 2000),
            renderer_max_message_chars=_env_int("WEIXIN_RENDERER_MAX_MESSAGE_CHARS", 3000),
            streaming_card_enabled=_env_bool("WEIXIN_STREAMING_CARD_ENABLED", False),
            streaming_card_template_uuid=_env("WEIXIN_STREAMING_CARD_TEMPLATE_UUID", ""),
            streaming_card_max_chars=_env_int("WEIXIN_STREAMING_CARD_MAX_CHARS", 8000),
            streaming_card_push_interval=_env_float("WEIXIN_STREAMING_CARD_PUSH_INTERVAL", 0.5),
            streaming_card_push_min_chars=_env_int("WEIXIN_STREAMING_CARD_PUSH_MIN_CHARS", 20),
            allowed_users=allowed,
        )

    @property
    def resolved_state_dir(self) -> Path:
        """解析状态目录，默认 ~/.weixinbot/"""
        if self.state_dir:
            return Path(self.state_dir).expanduser()
        return Path.home() / ".weixinbot"
