## ADDED Requirements

### Requirement: Hermes Agent Adapter
系统 SHALL 提供 HermesAdapter，通过 SSE 流式连接 Hermes Agent。

#### Scenario: 创建会话
- **WHEN** 用户进入 Hermes 模式
- **THEN** HermesAdapter SHALL 调用 Hermes API 创建新对话会话

#### Scenario: 发送消息
- **WHEN** 用户发送消息
- **THEN** HermesAdapter SHALL 通过 SSE 流式发送到 Hermes API，解析 JSON delta，通过 EventBus emit ResponseStart/Chunk/End 事件

#### Scenario: 错误处理
- **WHEN** SSE 连接断开或返回错误
- **THEN** HermesAdapter SHALL emit ResponseError 事件

### Requirement: OpenCode Agent Adapter
系统 SHALL 提供 OpenCodeAdapter，对接 OpenCode serve API，通过 SSE 持久连接消费事件流，并将其转换为 EventBus 上可单元测试的 ResponseStart/ResponseChunk/ResponseEnd/ResponseError 与 PermissionRequest。

#### State Machine: OpenCode sessions

**States (per user):**

- **IDLE**: 无活跃 session；无 pending permission；无 chunk buffer；无 abort_flag。
- **CONNECTING**: 正在建立本次交互：创建/选定 session、注册 SSE 回调、并准备发起 HTTP prompt 请求。
- **STREAMING**: prompt 请求已成功返回；正在接收 SSE 事件并 emit ResponseChunk。
- **AWAITING_PERMISSION**: 收到 `permission.updated` 后进入；等待用户 `/approve` 或 `/reject`；启用 30s 超时。
- **ABORTING**: 已发起中止；abort_flag 已置位；MUST 忽略该 session 的后续 SSE 流式事件；等待 abort 请求返回并收尾。
- **DONE/ERROR**: 终止态；DONE 表示正常结束/用户拒绝/中止完成；ERROR 表示错误终止。两者都 MUST 清理并回到 IDLE。

**Trigger events (test inputs):**

- `user.send(message)`
- `user.abort`
- `user.approve` / `user.reject`
- `sse.event(type, payload)` where type in:
  - `message.part.delta` (增量文本 chunk)
  - `tool.start` / `tool.end`
  - `permission.updated`
  - `session.idle` (完成)
  - `session.error` (错误)
- `sse.disconnected(reason)`
- `timer.chunk_buffer_flush` (5s)
- `timer.permission_timeout` (30s)
- `timer.sse_idle_timeout` (5m no events)

**Guards / invariants (MUST, testable):**

- Per-user `asyncio.Lock` MUST serialize `user.send` and `user.abort` so emitted events never interleave across concurrent calls from the same user.
- `abort_flag` MUST be set **before** sending any HTTP request that can race with SSE events (including prompt and abort).
- While state is **ABORTING** or **DONE/ERROR**, adapter MUST ignore all SSE streaming events for that session (no ResponseChunk emitted for them).
- For out-of-order handling, streaming chunks MUST carry a monotonic integer `seq` in payload; if `seq` is missing, adapter MUST treat arrival order as authoritative and MUST NOT buffer/reorder that event type.

**Transitions (trigger → from → to, with guards):**

- `user.send(message)` → IDLE → CONNECTING (guard: acquire per-user lock)
- prompt HTTP success → CONNECTING → STREAMING (guard: abort_flag == false)
- prompt HTTP failure → CONNECTING → ERROR
- `permission.updated` → STREAMING → AWAITING_PERMISSION (guard: abort_flag == false)
- `user.approve` → AWAITING_PERMISSION → STREAMING (guard: permission not timed out)
- `user.reject` → AWAITING_PERMISSION → DONE (guard: permission not timed out)
- `timer.permission_timeout` → AWAITING_PERMISSION → ERROR
- `session.idle` → STREAMING → DONE
- `session.error` → STREAMING/CONNECTING/AWAITING_PERMISSION → ERROR
- `sse.disconnected(reason)` → STREAMING/AWAITING_PERMISSION → ERROR
- `timer.sse_idle_timeout` → STREAMING/AWAITING_PERMISSION → ERROR
- `user.abort` → IDLE → IDLE (no-op, see scenario)
- `user.abort` → CONNECTING/STREAMING/AWAITING_PERMISSION → ABORTING (guard: set abort_flag first)
- abort HTTP success → ABORTING → DONE
- abort HTTP failure → ABORTING → ERROR
- DONE/ERROR → IDLE after Session cleanup completes

#### Scenario: Normal flow (send → SSE deltas → End)
- **WHEN** state is IDLE and `user.send("hi")` is invoked
- **THEN** adapter MUST emit `ResponseStart` exactly once **before** issuing the HTTP prompt request, and state MUST transition to CONNECTING
- **WHEN** the HTTP prompt request returns success and `abort_flag==false`
- **THEN** state MUST transition to STREAMING
- **WHEN** `sse.event(message.part.delta, {seq:1, delta:"A"})` and then `sse.event(message.part.delta, {seq:2, delta:"B"})` are received
- **THEN** adapter MUST emit `ResponseChunk(text="A")` then `ResponseChunk(text="B")` (same session_id)
- **WHEN** `sse.event(session.idle, {})` is received
- **THEN** adapter MUST emit `ResponseEnd` exactly once and MUST perform Session cleanup

#### Scenario: Out-of-order chunks (5s buffer window, 100 max, flush on timeout)
- **WHEN** state is STREAMING and adapter receives `sse.event(message.part.delta, {seq:2, delta:"B"})` before `sse.event(message.part.delta, {seq:1, delta:"A"})`
- **THEN** adapter MUST buffer seq=2 and MUST NOT emit any ResponseChunk for seq=2 until seq=1 is emitted or `timer.chunk_buffer_flush` fires
- **WHEN** `sse.event(message.part.delta, {seq:1, delta:"A"})` arrives within 5 seconds
- **THEN** adapter MUST emit `ResponseChunk(text="A")` then `ResponseChunk(text="B")` (ordered by seq)
- **WHEN** the earliest buffered chunk has waited 5 seconds (`timer.chunk_buffer_flush`) and ordering gaps still exist
- **THEN** adapter MUST flush buffered chunks in ascending seq order (even if gaps remain) and MUST continue STREAMING
- **WHEN** buffered streaming events exceed 100 entries at any time
- **THEN** adapter MUST emit `ResponseError(error contains "buffer overflow")`, state MUST transition to ERROR, and MUST perform Session cleanup

#### Scenario: Abort during streaming (race-protected)
- **WHEN** state is STREAMING and `user.abort` is invoked
- **THEN** adapter MUST set `abort_flag=true` **before** sending the HTTP abort request, state MUST transition to ABORTING, and adapter MUST ignore subsequent SSE streaming events for that session
- **WHEN** after abort is requested, `sse.event(message.part.delta, {seq:999, delta:"late"})` is received
- **THEN** adapter MUST emit no `ResponseChunk` for that event
- **WHEN** the HTTP abort request returns success
- **THEN** adapter MUST emit `ResponseEnd` exactly once (if not already emitted), state MUST transition to DONE, and MUST perform Session cleanup

#### Scenario: Abort before session created (no active session)
- **WHEN** state is IDLE and `user.abort` is invoked
- **THEN** adapter MUST return immediately with the exact message `"未找到活跃会话"`, MUST NOT send any HTTP request, and MUST NOT emit `ResponseEnd`

#### Scenario: Double abort is idempotent
- **WHEN** `user.abort` is invoked twice for the same user while the first abort is already in progress (state ABORTING)
- **THEN** the second call MUST be a no-op: it MUST NOT send a second HTTP abort request, MUST NOT emit an additional `ResponseEnd`/`ResponseError`, and MUST return the exact message `"任务已中止"`

#### Scenario: Abort while awaiting permission
- **WHEN** state is AWAITING_PERMISSION and a pending permission exists, then `user.abort` is invoked
- **THEN** adapter MUST cancel the permission wait (stop the 30s timer), MUST clear the pending permission record, MUST transition to ABORTING, and MUST emit `ResponseEnd` exactly once

#### Scenario: Permission flow (updated → approve/reject)
- **WHEN** state is STREAMING and `sse.event(permission.updated, {id:"perm1", ...})` is received
- **THEN** adapter MUST emit `PermissionRequest(permission_id="perm1")`, state MUST transition to AWAITING_PERMISSION, and a 30s permission timeout MUST start
- **WHEN** within 30 seconds user sends `/approve` (mapped to `user.approve`)
- **THEN** adapter MUST send exactly one HTTP permission reply request with JSON `{reply:"allow"}` and state MUST transition back to STREAMING
- **WHEN** within 30 seconds user sends `/reject` (mapped to `user.reject`)
- **THEN** adapter MUST send exactly one HTTP permission reply request with JSON `{reply:"deny"}`, MUST emit `ResponseEnd` exactly once, state MUST transition to DONE, and MUST perform Session cleanup

#### Scenario: Late permission response is ignored
- **WHEN** state is AWAITING_PERMISSION and 30 seconds elapse without approve/reject (`timer.permission_timeout`)
- **THEN** adapter MUST emit `ResponseError(error contains "permission timeout")`, state MUST transition to ERROR, and MUST perform Session cleanup
- **WHEN** after cleanup user sends `/approve` or `/reject`
- **THEN** adapter MUST NOT send any HTTP permission reply request and MUST return the exact message `"权限请求已过期"`

#### Scenario: SSE connection timeout (5 minutes no events)
- **WHEN** state is STREAMING or AWAITING_PERMISSION and no SSE events are received for 5 minutes (`timer.sse_idle_timeout`)
- **THEN** adapter MUST emit `ResponseError(error contains "sse idle timeout")`, state MUST transition to ERROR, and MUST perform Session cleanup

#### Scenario: SSE connection drop (immediate error)
- **WHEN** state is STREAMING or AWAITING_PERMISSION and the SSE stream disconnects (`sse.disconnected("network")`)
- **THEN** adapter MUST emit `ResponseError(error contains "network")`, state MUST transition to ERROR, and MUST perform Session cleanup

#### Scenario: Tool call display (tool.start/tool.end)
- **WHEN** state is STREAMING and `sse.event(tool.start, {tool_name:"read", input:{filePath:"/a.txt"}})` is received
- **THEN** adapter MUST emit `ResponseChunk(channel="tool")` whose `text` starts with `[tool:start] read` and includes `filePath=/a.txt`
- **WHEN** `sse.event(tool.end, {tool_name:"read", output:"L1\nL2\nL3"})` is received
- **THEN** adapter MUST emit `ResponseChunk(channel="tool")` whose `text` starts with `[tool:end] read` and includes at most the first 10 lines of output

#### Scenario: Concurrent messages are serialized per user
- **WHEN** two coroutines invoke `user.send(...)` concurrently for the same user
- **THEN** adapter MUST acquire a per-user `asyncio.Lock` so the second call MUST NOT emit `ResponseStart` until the first session has reached DONE/ERROR and cleanup completed
- **THEN** during the overlap window, emitted `ResponseChunk` events MUST reference exactly one active session_id at a time (no interleaving)

#### Scenario: Session cleanup clears all per-user state maps
- **WHEN** a session transitions to DONE or ERROR (including abort)
- **THEN** adapter MUST clear all per-user state: active session id, per-user lock-held flags (if any), abort_flag, pending permission, chunk buffer, and last-event timestamp
- **WHEN** after cleanup the same user invokes `user.abort`
- **THEN** adapter MUST behave as "no active session" and return the exact message `"未找到活跃会话"`

### Requirement: Adapter Registration
系统 SHALL 支持动态注册 Agent 适配器。

#### Scenario: 注册新适配器
- **WHEN** 调用 `mode_manager.register_adapter(my_adapter)`
- **THEN** 系统 SHALL 将适配器注册到模式路由表，用户可通过 `/{adapter.name}` 进入该模式

#### Scenario: 列出模式
- **WHEN** 用户发送 `/modes`
- **THEN** 系统 SHALL 列出所有已注册的适配器名称和描述
