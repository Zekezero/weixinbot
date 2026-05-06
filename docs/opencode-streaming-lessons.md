# OpenCode 流式输出踩坑记录

本文档记录了对接 OpenCode serve SSE 流式输出时遇到的关键问题及解决方案。

## 1. 竞态条件：用户快速发消息

**问题**：用户在 Agent 还在响应时快速发送第二条消息，导致两个 SSE 流交叉，输出混乱。

**解决**：
- 每用户 `asyncio.Lock` 锁（`_chat_key` 粒度）
- `_busy_users` 集合标记忙碌状态
- 忙碌时新消息静默丢弃（避免 SSE 输出交叉/状态混乱）

```python
if user_id in self._busy_users:
    logger.info("send: 用户 %s 忙碌，消息丢弃", user_id)
    return ""
```

## 2. Abort 竞态：先标记再请求

**问题**：发送 abort HTTP 请求期间，SSE 可能还在推送事件，导致 abort 后仍有内容输出。

**解决**：
- `abort_flag`（`_aborted_sessions` 集合）**必须在发送 HTTP abort 请求之前设置**
- SSE 回调检查 abort 状态是第一步，命中即 return

```python
# 正确顺序：先标记，再发请求
self._aborted_sessions.add(oc_sid)  # ← 先
resp = await client.post(f"{url}/session/{oc_sid}/abort")  # ← 后
```

## 3. SSE sessionID 位置不固定

**问题**：不同事件类型的 `sessionID` 字段位置不一致：
- `message.part.delta`: 在 `properties.sessionID`
- `message.part.updated`: 在 `properties.part.sessionID`
- 某些事件: 在 `properties.info.sessionID`

**解决**：多级 fallback 查找：
```python
session_id = properties.get("sessionID", "")
if not session_id:
    part = properties.get("part")
    if isinstance(part, dict):
        session_id = part.get("sessionID", "")
    if not session_id:
        info = properties.get("info")
        if isinstance(info, dict):
            session_id = info.get("sessionID", "")
```

## 4. SSE 连接断开与重连

**问题**：长时间无事件时 SSE 连接被服务端/中间件断开。

**解决**：
- `heartbeat_timeout = 60s` — 超过 60s 无数据视为断开
- 指数退避重连：1s → 2s → 4s → ... → 30s (最大)
- 重连成功后重置退避时间

## 5. 权限请求中断处理

**问题**：用户在等待权限审批时发送 `/abort`，需要同时取消权限等待和中止任务。

**当前实现**：
- `_pending_permissions` 记录 per-user 待审批权限
- 用户通过 `/approve` 或 `/reject` 响应
- abort 时标记 `_aborted_sessions`，后续 SSE 事件（包括权限相关）被忽略
- **注意**：当前实现中 abort 不会主动清理 `_pending_permissions`，且无权限等待超时机制（spec 中定义了 30s 超时，尚未实现）

**待改进**：
- abort 时应显式清理 `_pending_permissions[user_id]`
- 添加权限等待超时定时器（30s），超时后 emit ResponseError

## 6. 工具输出中的元数据噪声

**问题**：OpenCode 的 `task` 工具输出包含大量内部元数据（task_id、session_id 等），显示给用户无意义。

**解决**：
- `_TASK_META_PREFIXES` 前缀列表过滤
- 逐行检查，匹配前缀的行不显示
- 过滤后去掉首尾空行

## 7. destroy_session 必须清理所有关联状态

**问题**：`/exit` 退出模式后，SSE 回调可能还在触发，导致日志报错或状态不一致。

**解决**：`destroy_session` 必须清理全部映射：
```python
async def destroy_session(self, session_id: str) -> None:
    self._sse.unregister(oc_sid)
    user_id = self._oc_to_user.pop(oc_sid, None)
    self._oc_to_chat.pop(oc_sid, None)
    self._oc_to_session.pop(oc_sid, None)
    self._aborted_sessions.discard(oc_sid)
    if user_id:
        self._busy_users.discard(user_id)
        self._pending_permissions.pop(user_id, None)
```

## 8. 事件分类优先级

**问题**：SSE 事件类型繁多，全部处理会带来复杂度和性能问题。

**解决**：三级分类：
- **CRITICAL**: `permission.updated`, `session.error`, `session.idle` — 必须处理
- **STREAMING**: `message.part.delta`（有 delta）、`message.part.updated`（tool/step）— 流式显示
- **IGNORED**: 其他所有事件 — 直接跳过

## 总结

核心原则：
1. **先标记后操作** — 所有涉及竞态的状态变更必须在 HTTP 请求之前完成
2. **防御性字段查找** — SSE payload 结构不要假设固定位置
3. **优雅降级** — 连接断开/超时不崩溃，重连+退避
4. **完整清理** — session 销毁时清理所有关联映射，不留残余状态
