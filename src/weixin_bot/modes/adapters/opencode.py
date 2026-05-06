"""OpenCode Agent adapter — async task model + persistent SSE event stream."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from enum import Enum
from typing import Any, Awaitable, Callable

import httpx

from weixin_bot.config import WeixinBotConfig
from weixin_bot.modes.adapter import AgentAdapter, MessageContext
from weixin_bot.modes.events import (
    EventBus,
    ModeEvent,
    ResponseChunk,
    ResponseEnd,
    ResponseError,
    ResponseStart,
)

logger = logging.getLogger("weixin_bot.modes.adapters.opencode")


# ── 事件分类 ──────────────────────────────────────────


class EventPriority(Enum):
    CRITICAL = "critical"
    STREAMING = "streaming"
    IGNORED = "ignored"


def classify_event(event_type: str, properties: dict[str, Any]) -> EventPriority:
    """SSE 事件分类。"""
    if event_type in ("permission.updated", "session.error", "session.idle"):
        return EventPriority.CRITICAL

    if event_type == "message.part.delta" and properties.get("delta"):
        return EventPriority.STREAMING

    if event_type == "message.part.updated":
        part = properties.get("part", {})
        if isinstance(part, dict) and part.get("type") in ("tool", "step-start"):
            return EventPriority.STREAMING

    return EventPriority.IGNORED


# ── 事件格式化 ────────────────────────────────────────


def format_permission(properties: dict[str, Any]) -> str:
    title = properties.get("title", "")
    perm_type = properties.get("type", "unknown")
    pattern = properties.get("pattern", "")
    if title:
        detail = title
    elif pattern:
        detail = f"{perm_type}: `{pattern}`"
    else:
        detail = perm_type
    return (
        f"OpenCode 请求权限: {detail}\n"
        f"回复 /approve 允许 或 /reject 拒绝"
    )


def format_completion(diff_summary: str) -> str:
    if diff_summary:
        return f"\n\n---\n✅ 完成 | {diff_summary}"
    return "\n\n---\n✅ 完成"


# ── 工具显示（对齐 TUI）──

_TOOL_ICONS: dict[str, str] = {
    "read": "→", "view": "→", "glob": "✱", "grep": "✱",
    "write": "←", "edit": "←", "apply_patch": "%",
    "bash": "$", "execute": "$", "webfetch": "%",
    "websearch": "◈", "codesearch": "◇", "task": "│",
    "todowrite": "⚙", "question": "?", "skill": "→",
}

_TOOL_PENDING: dict[str, str] = {
    "read": "Reading file...", "view": "Reading file...",
    "glob": "Finding files...", "grep": "Searching content...",
    "write": "Preparing write...", "edit": "Preparing edit...",
    "bash": "Writing command...", "execute": "Writing command...",
    "apply_patch": "Preparing patch...", "webfetch": "Fetching from the web...",
    "websearch": "Searching web...", "codesearch": "Searching code...",
    "task": "Delegating...", "todowrite": "Updating todos...",
    "skill": "Loading skill...",
}

_MAX_OUTPUT_LINES = 10
_MAX_TASK_OUTPUT_LINES = 30

_TASK_META_PREFIXES = (
    "Background task launched", "Background Task ID:", "Description:",
    "Agent:", "Status:", "System notifies", "Do NOT call",
    "<task_metadata>", "</task_metadata>", "session_id:",
    "task_id:", "background_task_id:", "subagent:", "to continue:",
)


def _is_task_metadata_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    return any(stripped.startswith(p) for p in _TASK_META_PREFIXES)


def _shorten_path(path: str) -> str:
    if not path:
        return ""
    norm = path.replace("\\", "/")
    cwd = os.getcwd().replace("\\", "/").rstrip("/") + "/"
    if norm.startswith(cwd):
        return norm[len(cwd):]
    return path


def _extra_params(input_args: dict[str, Any], omit: set[str]) -> str:
    parts = []
    for k, v in input_args.items():
        if k in omit:
            continue
        if isinstance(v, (str, int, float, bool)):
            parts.append(f"{k}={v}")
    return f" [{', '.join(parts)}]" if parts else ""


def _format_tool_label(tool_name: str, input_args: Any) -> str:
    icon = _TOOL_ICONS.get(tool_name, "→")
    pending = _TOOL_PENDING.get(tool_name, "Working...")
    if not isinstance(input_args, dict) or not input_args:
        return f"{icon} {pending}"
    return f"{icon} {_format_tool_inline(tool_name, input_args)}"


def _format_tool_inline(tool_name: str, input_args: dict[str, Any]) -> str:
    path = _shorten_path(
        input_args.get("filePath", "")
        or input_args.get("file_path", "")
        or input_args.get("path", "")
    )

    if tool_name in ("read", "view"):
        extra = _extra_params(input_args, {"filePath", "file_path", "path"})
        return f"Read {path or '.'}{extra}"
    if tool_name == "glob":
        pattern = input_args.get("pattern", "")
        p = _shorten_path(input_args.get("path", ""))
        return f'Glob "{pattern}"' + (f" in {p}" if p else "")
    if tool_name == "grep":
        pattern = input_args.get("pattern", "")
        p = _shorten_path(input_args.get("path", ""))
        extra = _extra_params(input_args, {"pattern", "path"})
        return f'Grep "{pattern}"' + (f" in {p}" if p else "") + extra
    if tool_name in ("write",):
        return f"Write {path}"
    if tool_name in ("edit",):
        return f"Edit {path}"
    if tool_name in ("bash", "execute"):
        cmd = input_args.get("command", "")
        if len(cmd) > 80:
            cmd = cmd[:80] + "..."
        return cmd.replace("\n", " ") if cmd else tool_name
    if tool_name == "webfetch":
        return input_args.get("url", "")
    if tool_name in ("websearch",):
        return f'Exa Web Search "{input_args.get("query", "")}"'
    if tool_name in ("codesearch",):
        return f'Exa Code Search "{input_args.get("query", "")}"'
    if tool_name == "skill":
        name = input_args.get("name", "")
        return f'Skill "{name}"' if name else "skill"
    if tool_name == "task":
        desc = input_args.get("description", "")
        agent = input_args.get("subagent_type", "")
        if agent and desc:
            return f"{agent}: {desc}"
        return desc or "Delegating..."
    return f"{tool_name} {path}" if path else tool_name


def _format_tool_response(tool_name: str, state: dict[str, Any]) -> str:
    title = state.get("title", "")
    input_args = state.get("input", {})
    output = state.get("output", "")

    if tool_name in ("write",):
        path = _shorten_path(title or (input_args.get("filePath", "") if isinstance(input_args, dict) else ""))
        fname = path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1] if path else ""
        content = input_args.get("content", "") if isinstance(input_args, dict) else ""
        if not content:
            return ""
        lines = content.split("\n")
        preview = lines[:_MAX_OUTPUT_LINES]
        numbered = [f"  {i} {ln}" for i, ln in enumerate(preview, 1)]
        if len(lines) > _MAX_OUTPUT_LINES:
            numbered.append("  …")
        return f"\n# Wrote {fname}\n\n" + "\n".join(numbered) + "\n\n"

    if tool_name in ("edit",):
        path = _shorten_path(title or (input_args.get("filePath", "") if isinstance(input_args, dict) else ""))
        fname = path.rsplit("\\", 1)[-1].rsplit("/", 1)[-1] if path else ""
        old_str = input_args.get("oldString", "") if isinstance(input_args, dict) else ""
        new_str = input_args.get("newString", "") if isinstance(input_args, dict) else ""
        if not old_str and not new_str:
            return ""
        diff_lines: list[str] = []
        if old_str:
            for ln in old_str.split("\n")[:_MAX_OUTPUT_LINES]:
                diff_lines.append(f"  - {ln}")
        if new_str:
            for ln in new_str.split("\n")[:_MAX_OUTPUT_LINES]:
                diff_lines.append(f"  + {ln}")
        if len(old_str.split("\n")) + len(new_str.split("\n")) > _MAX_OUTPUT_LINES:
            diff_lines.append("  …")
        return f"\n# Edited {fname}\n\n" + "\n".join(diff_lines) + "\n\n"

    if tool_name in ("bash", "execute") and output:
        lines_out = output.split("\n")
        preview = lines_out[:_MAX_OUTPUT_LINES]
        if len(lines_out) > _MAX_OUTPUT_LINES:
            preview.append("…")
        return "\n" + "\n".join(preview) + "\n"

    if tool_name == "task" and output:
        filtered = [ln for ln in output.split("\n") if not _is_task_metadata_line(ln)]
        while filtered and not filtered[0].strip():
            filtered.pop(0)
        while filtered and not filtered[-1].strip():
            filtered.pop()
        if not filtered:
            return ""
        preview = filtered[:_MAX_TASK_OUTPUT_LINES]
        if len(filtered) > _MAX_TASK_OUTPUT_LINES:
            preview.append("…")
        return "\n" + "\n".join(preview) + "\n"

    return ""


def format_error(properties: dict[str, Any]) -> str:
    error = properties.get("error", "未知错误")
    if isinstance(error, dict):
        data = error.get("data", {})
        msg = data.get("message", "") if isinstance(data, dict) else ""
        if not msg:
            msg = error.get("name", str(error))
        error = msg
    return f"❌ {error}"


# ── 权限请求事件 ──────────────────────────────────────


@dataclass
class PermissionRequest(ModeEvent):
    permission_id: str = ""
    description: str = ""


# ── SSE 事件流客户端 ──────────────────────────────────


EventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


class OpenCodeSSEClient:
    """持久 SSE 连接，订阅 GET /event，按 sessionID 分发事件。"""

    def __init__(
        self,
        base_url: str,
        auth: httpx.BasicAuth | None = None,
        timeout: int = 120,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._auth = auth
        self._timeout = timeout
        self._callbacks: dict[str, EventCallback] = {}
        self._task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._base_delay = 1.0
        self._max_delay = 30.0
        self._heartbeat_timeout = 60.0

    def register(self, session_id: str, callback: EventCallback) -> None:
        self._callbacks[session_id] = callback

    def unregister(self, session_id: str) -> None:
        self._callbacks.pop(session_id, None)

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _run_loop(self) -> None:
        delay = self._base_delay
        while not self._stop_event.is_set():
            try:
                await self._connect_and_read()
                delay = self._base_delay
            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("SSE 连接异常，%.1fs 后重连", delay)

            if self._stop_event.is_set():
                return

            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=delay)
                return
            except asyncio.TimeoutError:
                pass

            delay = min(delay * 2, self._max_delay)

    async def _connect_and_read(self) -> None:
        url = f"{self._base_url}/event"
        timeout = httpx.Timeout(timeout=None, read=self._heartbeat_timeout)

        async with httpx.AsyncClient(timeout=timeout, auth=self._auth) as client:
            async with client.stream("GET", url) as response:
                if response.status_code != 200:
                    body = await response.aread()
                    raise RuntimeError(
                        f"SSE 连接失败 {response.status_code}: "
                        f"{body.decode('utf-8', errors='replace')}"
                    )

                logger.info("SSE 已连接: %s", url)

                async for line in response.aiter_lines():
                    if self._stop_event.is_set():
                        return
                    if not line or not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    try:
                        payload = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    await self._dispatch(payload)

    async def _dispatch(self, payload: dict[str, Any]) -> None:
        event_type = payload.get("type", "")
        properties = payload.get("properties", {})

        if event_type in ("server.heartbeat", "server.connected"):
            return

        session_id = properties.get("sessionID", "")
        if not session_id:
            part = properties.get("part")
            if isinstance(part, dict):
                session_id = part.get("sessionID", "")
            if not session_id:
                info = properties.get("info")
                if isinstance(info, dict):
                    session_id = info.get("sessionID", "")
        if not session_id:
            return

        callback = self._callbacks.get(session_id)
        if callback is None:
            return

        try:
            await callback(event_type, properties)
        except Exception:
            logger.exception("事件回调失败: type=%s session=%s", event_type, session_id)


# ── OpenCode Adapter ──────────────────────────────────


@dataclass
class _PendingPermission:
    permission_id: str
    session_id: str
    description: str


class OpenCodeAdapter(AgentAdapter):
    """OpenCode Agent adapter — 流式输出 + 异步任务模型。"""

    name: str = "opencode"
    display_name: str = "OpenCode"

    def __init__(self, config: WeixinBotConfig, bus: EventBus) -> None:
        super().__init__(bus)
        self._config = config
        self._base_url = config.opencode_base_url.rstrip("/")

        self._auth: httpx.BasicAuth | None = None

        self._oc_to_user: dict[str, str] = {}
        self._oc_to_chat: dict[str, str] = {}
        self._oc_to_session: dict[str, str] = {}
        self._pending_permissions: dict[str, _PendingPermission] = {}
        self._busy_users: set[str] = set()
        self._aborted_sessions: set[str] = set()
        self._task_counter: int = 0

        self._sse = OpenCodeSSEClient(self._base_url, auth=self._auth, timeout=120)
        self._sse_started = False

    async def _ensure_sse(self) -> None:
        if not self._sse_started:
            await self._sse.start()
            self._sse_started = True

    def _http_client(self) -> httpx.AsyncClient:
        timeout = httpx.Timeout(timeout=120, read=120)
        return httpx.AsyncClient(timeout=timeout, auth=self._auth)

    # ── Session 生命周期 ──────────────────────────────

    async def create_session(self) -> str:
        await self._ensure_sse()
        async with self._http_client() as client:
            resp = await client.post(
                f"{self._base_url}/session",
                json={"title": "weixinbot-session"},
            )
            resp.raise_for_status()
            data = resp.json()

        oc_session_id = data.get("id", "")
        if not oc_session_id:
            raise RuntimeError("OpenCode 未返回 session ID")

        logger.info("create_session → %s", oc_session_id)
        return oc_session_id

    async def send(
        self,
        session_id: str,
        message: str,
        context: MessageContext,
        *,
        user_id: str,
    ) -> str:
        await self._ensure_sse()
        logger.info("send → session=%s user=%s msg=%s", session_id, user_id, message[:80])

        # 忙碌时静默丢弃（竞态保护）
        if user_id in self._busy_users:
            logger.info("send: 用户 %s 忙碌，消息丢弃", user_id)
            return ""

        oc_sid = session_id
        self._oc_to_user[oc_sid] = user_id
        self._oc_to_chat[oc_sid] = context.chat_id
        self._oc_to_session[oc_sid] = session_id
        self._aborted_sessions.discard(oc_sid)
        self._sse.register(oc_sid, self._on_sse_event)
        self._busy_users.add(user_id)

        await self._bus.emit(
            ResponseStart(
                user_id=user_id,
                mode=self.name,
                session_id=session_id,
                chat_id=context.chat_id,
            )
        )

        try:
            async with self._http_client() as client:
                resp = await client.post(
                    f"{self._base_url}/session/{oc_sid}/prompt_async",
                    json={"parts": [{"type": "text", "text": message}]},
                )
                if resp.status_code not in (200, 204):
                    error_text = resp.text
                    raise RuntimeError(f"prompt_async 失败 {resp.status_code}: {error_text}")
        except Exception as exc:
            self._busy_users.discard(user_id)
            await self._bus.emit(
                ResponseError(
                    user_id=user_id, mode=self.name, session_id=session_id,
                    error=str(exc), chat_id=context.chat_id,
                )
            )
            raise

        return ""

    async def destroy_session(self, session_id: str) -> None:
        oc_sid = session_id
        self._sse.unregister(oc_sid)
        # 清理该 session 关联的所有状态
        user_id = self._oc_to_user.pop(oc_sid, None)
        self._oc_to_chat.pop(oc_sid, None)
        self._oc_to_session.pop(oc_sid, None)
        self._aborted_sessions.discard(oc_sid)
        if user_id:
            self._busy_users.discard(user_id)
            self._pending_permissions.pop(user_id, None)

    # ── 权限交互 ──────────────────────────────────────

    async def approve(self, user_id: str) -> str:
        pending = self._pending_permissions.pop(user_id, None)
        if not pending:
            return "没有待处理的权限请求"
        async with self._http_client() as client:
            resp = await client.post(
                f"{self._base_url}/permission/{pending.permission_id}/reply",
                json={"reply": "allow"},
            )
            resp.raise_for_status()
        return "已批准权限请求"

    async def reject(self, user_id: str) -> str:
        pending = self._pending_permissions.pop(user_id, None)
        if not pending:
            return "没有待处理的权限请求"
        async with self._http_client() as client:
            resp = await client.post(
                f"{self._base_url}/permission/{pending.permission_id}/reply",
                json={"reply": "deny"},
            )
            resp.raise_for_status()
        return "已拒绝权限请求"

    async def abort(self, user_id: str) -> str:
        oc_sid = self._find_oc_session(user_id)
        if not oc_sid:
            return "未找到活跃会话"

        # 竞态保护：先标记 abort，再发请求
        self._busy_users.discard(user_id)
        self._aborted_sessions.add(oc_sid)

        logger.info("abort: session=%s user=%s", oc_sid, user_id)
        try:
            async with self._http_client() as client:
                resp = await client.post(f"{self._base_url}/session/{oc_sid}/abort")
                logger.info("abort: 响应 %s %s", resp.status_code, resp.text[:200])
                resp.raise_for_status()
        except Exception as exc:
            logger.exception("abort 请求失败: session=%s", oc_sid)
            self._busy_users.add(user_id)
            self._aborted_sessions.discard(oc_sid)
            return f"中止失败: {exc}"

        return "任务已中止"

    def is_busy(self, user_id: str) -> bool:
        return user_id in self._busy_users

    # ── SSE 事件回调 ──────────────────────────────────

    async def _on_sse_event(self, event_type: str, properties: dict[str, Any]) -> None:
        oc_sid = properties.get("sessionID", "")
        if not oc_sid:
            part = properties.get("part")
            if isinstance(part, dict):
                oc_sid = part.get("sessionID", "")

        if oc_sid in self._aborted_sessions:
            return

        user_id = self._oc_to_user.get(oc_sid)
        if not user_id:
            return

        chat_id = self._oc_to_chat.get(oc_sid) or user_id
        mapped_sid = self._oc_to_session.get(oc_sid) or oc_sid

        priority = classify_event(event_type, properties)
        if priority == EventPriority.IGNORED:
            return

        # ── 流式增量 ──
        if priority == EventPriority.STREAMING:
            chunk_text = ""
            channel = "main"

            if event_type == "message.part.delta":
                delta = properties.get("delta", "")
                if not delta:
                    return
                field = properties.get("field", "text")
                if field == "reasoning":
                    channel = "main"
                    chunk_text = f"💭 {delta}"
                else:
                    channel = "main"
                    chunk_text = delta

            elif event_type == "message.part.updated":
                part = properties.get("part", {})
                if not isinstance(part, dict):
                    return
                part_type = part.get("type", "")
                if part_type == "tool":
                    tool_name = part.get("tool", "")
                    state = part.get("state", {})
                    if not isinstance(state, dict):
                        return
                    status = state.get("status", "")

                    if tool_name == "task":
                        part_id = part.get("partID", "")
                        if part_id:
                            channel = f"task:{part_id}"
                        else:
                            self._task_counter += 1
                            channel = f"task:anon_{self._task_counter}"
                    else:
                        channel = "main"

                    if status == "running":
                        chunk_text = _format_tool_label(tool_name, state.get("input", {})) + "\n"
                    elif status == "completed":
                        block = _format_tool_response(tool_name, state)
                        if block:
                            chunk_text = block

            if not chunk_text:
                return

            await self._bus.emit(
                ResponseChunk(
                    user_id=user_id, mode=self.name, session_id=mapped_sid,
                    text=chunk_text, channel=channel,
                )
            )
            return

        # ── CRITICAL: 权限请求 ──
        if event_type == "permission.updated":
            perm_id = properties.get("id", "")
            description = format_permission(properties)
            self._pending_permissions[user_id] = _PendingPermission(
                permission_id=perm_id, session_id=oc_sid, description=description,
            )
            await self._bus.emit(
                PermissionRequest(
                    user_id=user_id, mode=self.name, session_id=mapped_sid,
                    permission_id=perm_id, description=description,
                )
            )
            return

        # ── CRITICAL: 错误 ──
        if event_type == "session.error":
            if user_id not in self._busy_users:
                return
            self._busy_users.discard(user_id)
            error_text = format_error(properties)
            await self._bus.emit(
                ResponseError(
                    user_id=user_id, mode=self.name, session_id=mapped_sid,
                    error=error_text, chat_id=chat_id,
                )
            )
            return

        # ── CRITICAL: 完成 ──
        if event_type == "session.idle":
            if user_id not in self._busy_users:
                return
            self._busy_users.discard(user_id)
            diff_summary = await self._fetch_diff(oc_sid)
            tail = format_completion(diff_summary)
            await self._bus.emit(
                ResponseChunk(
                    user_id=user_id, mode=self.name, session_id=mapped_sid,
                    text=tail,
                )
            )
            await self._bus.emit(
                ResponseEnd(
                    user_id=user_id, mode=self.name, session_id=mapped_sid,
                    full_text="", chat_id=chat_id,
                )
            )
            return

    async def _fetch_diff(self, oc_session_id: str) -> str:
        try:
            async with self._http_client() as client:
                resp = await client.get(f"{self._base_url}/session/{oc_session_id}")
                if resp.status_code == 200:
                    data = resp.json()
                    summary = data.get("summary", {})
                    if isinstance(summary, dict):
                        adds = summary.get("additions", 0)
                        dels = summary.get("deletions", 0)
                        files = summary.get("files", 0)
                        if adds or dels or files:
                            return f"+{adds} -{dels} ({files} files)"
        except Exception:
            logger.debug("获取 diff 失败: session=%s", oc_session_id)
        return ""

    def _find_oc_session(self, user_id: str) -> str | None:
        for oc_sid, uid in self._oc_to_user.items():
            if uid == user_id:
                return oc_sid
        return None

    async def shutdown(self) -> None:
        await self._sse.stop()
