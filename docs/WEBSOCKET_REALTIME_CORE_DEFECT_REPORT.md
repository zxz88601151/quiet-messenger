# WebSocket Realtime Core — 缺陷报告

> 基于 2026-08-25 READ-ONLY RECON 全仓审计生成。
> 范围：Backend / Android (Flutter) / Desktop (PySide6) 三端 WebSocket 实时通信基础设施。
> 状态：仅记录，未修复。等待授权后进入实施阶段。

---

## 缺陷总览

| 编号 | 严重级 | 标题 | 影响端 | 状态 |
|------|--------|------|--------|------|
| DEF-RT-001 | 🔴 P0 阻断 | Desktop on_event 单播架构缺陷 | Desktop | 未修复 |
| DEF-RT-002 | 🔴 P0 阻断 | 本地后端与 Staging 代码不同步 | Backend | 未修复 |
| DEF-RT-003 | 🔴 P0 阻断 | Logout 不断开 WebSocket 连接 | Android + Desktop | 未修复 |
| DEF-RT-004 | 🟠 P1 重要 | Desktop 无 friend.request.created 实时处理 | Desktop | 未修复 |
| DEF-RT-005 | 🟠 P1 重要 | Desktop 无 presence.update 实时处理 | Desktop | 未修复 |
| DEF-RT-006 | 🟠 P1 重要 | Desktop 完全无 SoundService | Desktop | 未修复 |
| DEF-RT-007 | 🟠 P1 重要 | Desktop EventEnvelope 无类型安全检查 | Desktop | 未修复 |
| DEF-RT-008 | 🟠 P1 重要 | Desktop message.created 不播放提示音 | Desktop | 未修复 |
| DEF-RT-009 | 🟡 P2 增强 | 后端无全局定时连接清理任务 | Backend | 未修复 |
| DEF-RT-010 | 🟡 P2 增强 | 无离线恢复 / 事件回放机制 | 三端 | 未修复 |
| DEF-RT-011 | 🟡 P2 增强 | 同设备多连接顶替策略需确认 | Backend | 未修复 |
| DEF-RT-012 | 🟡 P2 增强 | 后端服务器重启后无重连引导事件 | Backend | 未修复 |

---

## P0 阻断级缺陷

### DEF-RT-001：Desktop on_event 单播架构缺陷

| 项 | 内容 |
|----|------|
| **严重级** | 🔴 P0 阻断 |
| **影响端** | Desktop (PySide6) |
| **文件** | `desktop/app/realtime/realtime_client.py` + `desktop/app/features/chat/message_state.py:45` |

**问题描述：**
`RealtimeClient.on_event` 是单一回调属性（`Callable[[EventEnvelope], None] | None`），不支持多播。`MessageController.__init__` 直接覆盖：
```python
self._realtime.on_event = self._on_event  # message_state.py:45
```
后果：
- 只有最后创建的 `MessageController` 能收到 WS 事件
- `FriendController` 完全无法订阅任何事件
- 未来 `PresenceController` 也无法订阅
- 打开多个会话时，只有最后一个会话能收到实时消息

**根因：**
Desktop RealtimeClient 设计时未考虑多消费者场景，与 Flutter 端的 `addEventListener()` 多播机制不对齐。

**复现方式：**
1. Desktop 登录后打开会话 A（创建 MessageController A，on_event = A._on_event）
2. 打开会话 B（创建 MessageController B，on_event = B._on_event，覆盖 A）
3. 会话 A 收到新消息 → A 收不到事件（on_event 已被 B 覆盖）

**建议修复：**
对齐 Flutter 实现，增加多播监听器列表：
```python
def add_event_listener(self, cb) -> Callable[[], None]: ...
def remove_event_listener(self, cb) -> None: ...
```
保留 `on_event` 兼容属性或废弃。

---

### DEF-RT-002：本地后端与 Staging 代码不同步

| 项 | 内容 |
|----|------|
| **严重级** | 🔴 P0 阻断 |
| **影响端** | Backend |
| **文件** | `backend/app/services/presence.py`（本地不存在）+ `backend/app/services/social_service.py`（本地无 friend.request.created 推送）+ `backend/app/routers/ws.py`（本地无 presence 调用） |

**问题描述：**
以下功能**仅存在于 Staging 服务器**（`/opt/v1.1-staging/backend/`），本地代码库 `E:\liaotianapp\backend` 中**不存在**：

1. **`presence.py`** — PresenceService 模块（用户在线状态跟踪 + 好友通知）
2. **`friend.request.created` WS 推送** — `social_service.create_friend_request()` 中的 `manager.send_to_user(receiver, make_event("friend.request.created", result))`
3. **`ws.py` presence 集成** — `presence.on_connect()` / `presence.on_disconnect()` 调用 + `SessionLocal` 导入

**根因：**
上一轮修复时直接在 Staging 服务器上打补丁，未同步回本地代码库。

**风险：**
- 本地 `pytest` 无法覆盖这些功能
- 下次部署时如果从本地代码构建，这些功能会丢失
- 代码审查无法进行
- 新开发者无法复现 Staging 行为

**建议修复：**
将 Staging 上的三个补丁同步回本地 `E:\liaotianapp\backend`，提交到版本控制。

---

### DEF-RT-003：Logout 不断开 WebSocket 连接

| 项 | 内容 |
|----|------|
| **严重级** | 🔴 P0 阻断 |
| **影响端** | Android (Flutter) + Desktop (PySide6) |
| **文件** | `flutter/lib/features/auth/auth_notifier.dart:88-100` + `desktop/app/features/auth/state.py` |

**问题描述：**
双端的 Logout 流程只清理 session/token，**不关闭 WebSocket 连接**：

**Android** (`auth_notifier.dart:88-100`)：
```dart
Future<void> logout() async {
  _beginLoading();
  try { await _repo.logout(); }
  on ApiException { /* 即使后端失败也清理本地 */ }
  finally {
    _session = null;
    _status = AuthState.unauthenticated;
    // ❌ 没有调用 _realtime.disconnect()
  }
}
```

**Desktop** (`auth/state.py`)：
类似，logout() 只清理 token/session，不调用 `realtime.disconnect()`。

**后果：**
- 登出后 WebSocket 连接仍保持在线
- 继续收到 `message.created` / `friend.request.created` 事件
- 再次登录后可能创建第二个连接（旧连接未关闭）
- 安全风险：已登出用户仍能接收实时数据

**根因：**
AuthNotifier/AuthController 不持有 RealtimeClient 引用，Logout 流程未纳入 WS 生命周期管理。

**建议修复：**
- Android：在 `app.dart` 中监听 AuthNotifier 状态变化，unauthenticated 时调用 `_realtime.disconnect()`；或在 AuthNotifier 中注入 RealtimeClient 引用
- Desktop：在 AuthController.logout() 中调用 `realtime.disconnect()`

---

## P1 重要缺陷

### DEF-RT-004：Desktop 无 friend.request.created 实时处理

| 项 | 内容 |
|----|------|
| **严重级** | 🟠 P1 重要 |
| **影响端** | Desktop |
| **文件** | `desktop/app/features/friends/state.py` |

**问题描述：**
`FriendController` 完全没有 WebSocket 事件订阅。好友请求列表只能通过 `load_requests()` 手动刷新获取，无实时推送。

对比 Android：`FriendNotifier.subscribeRealtime()` 已接入 `friend.request.created`，支持去重、初始同步排除、音效。

**后果：**
- Desktop 用户收到新好友请求时无实时通知
- 必须手动刷新好友请求页面才能看到新请求
- 与 Android 行为不一致

**建议修复：**
依赖 DEF-RT-001（多播）修复后，FriendController 订阅 `friend.request.created`，对齐 Android 的去重 + 初始同步排除逻辑。

---

### DEF-RT-005：Desktop 无 presence.update 实时处理

| 项 | 内容 |
|----|------|
| **严重级** | 🟠 P1 重要 |
| **影响端** | Desktop |
| **文件** | 无（Desktop 完全没有 Presence 模块） |

**问题描述：**
Desktop 端完全没有在线状态（Presence）模块：
- 无 `PresenceController` / `PresenceState`
- 无 `presence.update` 事件订阅
- 好友列表无在线/离线指示器

对比 Android：`PresenceNotifier` 已创建，订阅 `presence.update`，维护 user_id → online 映射。

**建议修复：**
新建 `desktop/app/features/presence/` 模块，对齐 Android PresenceNotifier 实现。

---

### DEF-RT-006：Desktop 完全无 SoundService

| 项 | 内容 |
|----|------|
| **严重级** | 🟠 P1 重要 |
| **影响端** | Desktop |
| **文件** | 无（Desktop 完全没有音效模块） |

**问题描述：**
Desktop 端完全没有音效播放服务：
- 无 `SoundService` 类
- 无 `friend_added.mp3` / `new_message.mp3` 资源
- 无任何音效播放调用

对比 Android：`SoundService` 单例已实现，支持音量/开关/前后台/节流，`friend_added.mp3` 和 `new_message.mp3` 已接入。

**建议修复：**
- 新建 Desktop SoundService（使用 PySide6 QSoundEffect 或 playsound）
- 添加音效资源文件
- 在 MessageController / FriendController 中接入

---

### DEF-RT-007：Desktop EventEnvelope 无类型安全检查

| 项 | 内容 |
|----|------|
| **严重级** | 🟠 P1 重要 |
| **影响端** | Desktop |
| **文件** | `desktop/app/realtime/event_envelope.py:27-33` |

**问题描述：**
Desktop `EventEnvelope.from_json()` 直接使用 `data.get("type", "")`，对非字符串类型（如 `type: 123`、`type: null`、`type: {}`）无校验：
```python
@classmethod
def from_json(cls, data):
    return cls(
        type=data.get("type", ""),       # ❌ type=123 时赋 int 给 str 字段
        id=data.get("id", ""),
        timestamp=data.get("timestamp", ""),
        payload=data.get("payload", {}) or {},
    )
```

对比 Android：`EventEnvelope.fromJson()` 已实现全字段类型安全（DEFECT-001/002/003 修复），非匹配类型抛出 `FormatException` 由调用方捕获。

**后果：**
- 后端发送 malformed event（如 `type: 123`）时，Desktop 可能静默创建类型错误的对象
- 后续 `evt.type == "message.created"` 比较可能因类型不匹配而静默失败
- 难以调试

**建议修复：**
对齐 Android 实现，增加字段类型校验，非匹配类型抛出 `ValueError`（对应 Android 的 FormatException），由 `RealtimeClient._loop` 捕获。

---

### DEF-RT-008：Desktop message.created 不播放提示音

| 项 | 内容 |
|----|------|
| **严重级** | 🟠 P1 重要 |
| **影响端** | Desktop |
| **文件** | `desktop/app/features/chat/message_state.py:117-124` |

**问题描述：**
Desktop `MessageController._on_event()` 收到 `message.created` 时只做 `_upsert(msg)`，**不播放提示音**，也**不排除自己发送的消息**：
```python
def _on_event(self, evt):
    if evt.type != "message.created": return
    payload = evt.payload or {}
    if payload.get("conversation_id") != self.conversation_id: return
    msg = Message.from_json(payload)
    self._upsert(msg)  # ❌ 无音效，无自己消息排除
```

对比 Android：`MessageNotifier._onEvent()` 检查 `msg.senderId != _currentUserId` 后播放 `SoundService.instance.playNewMessage()`。

**建议修复：**
依赖 DEF-RT-006（SoundService）修复后，在 `_on_event` 中增加自己消息排除 + 音效播放。

---

## P2 增强缺陷

### DEF-RT-009：后端无全局定时连接清理任务

| 项 | 内容 |
|----|------|
| **严重级** | 🟡 P2 增强 |
| **影响端** | Backend |
| **文件** | `backend/app/routers/ws.py:83` |

**问题描述：**
`sweep_stale()` 仅在新连接接入时调用一次（`ws.py:83`），无后台定时任务持续清理死连接。如果长时间没有新连接，stale 连接会一直保留在注册表中。

**建议修复：**
在 FastAPI lifespan 中启动后台任务，每 `WS_CLEANUP_INTERVAL_SECONDS`（默认 30s）调用一次 `manager.sweep_stale()`。

---

### DEF-RT-010：无离线恢复 / 事件回放机制

| 项 | 内容 |
|----|------|
| **严重级** | 🟡 P2 增强 |
| **影响端** | 三端 |
| **文件** | 无统一机制 |

**问题描述：**
当前无事件回放 / sequence number / last_received_event 机制。客户端断线期间丢失的事件无法通过 WebSocket 恢复，只能依赖客户端重新 GET REST API。

当前实际行为（隐式）：
- 重连后客户端重新进入页面时调用 REST API 刷新状态
- 但如果用户停留在当前页面，断线期间的新消息/好友请求不会自动刷新

**建议修复：**
定义明确的 reconnect → REST reconciliation 流程：
- WebSocket reconnect 成功后，触发各 Notifier 重新加载（loadFriends / loadRequests / loadMessages）
- 或后端实现基于 sequence 的事件回放（成本高，当前阶段可暂缓）

---

### DEF-RT-011：同设备多连接顶替策略需确认

| 项 | 内容 |
|----|------|
| **严重级** | 🟡 P2 增强 |
| **影响端** | Backend |
| **文件** | `backend/app/services/connection_manager.py:102-108` |

**问题描述：**
`manager.register()` 中，同一 `device_id` 的新连接会顶替旧连接（关闭旧连接的映射）。如果同一设备上的 App 因为网络切换创建了新连接但旧连接尚未完全关闭，可能导致旧连接被强制关闭。

需确认：这是否符合"一个用户允许多个设备连接"的需求？当前是"同 device_id 单连接，不同 device_id 多连接"。

**建议修复：**
确认产品需求后决定：
- 如果允许同设备多连接：移除顶替逻辑
- 如果不允许：当前行为正确，但需在文档中明确

---

### DEF-RT-012：后端服务器重启后无重连引导事件

| 项 | 内容 |
|----|------|
| **严重级** | 🟡 P2 增强 |
| **影响端** | Backend |
| **文件** | 无 |

**问题描述：**
后端进程重启后，所有 WebSocket 连接断开。客户端通过指数退避重连，但后端不发送任何"服务器已恢复"的引导事件。客户端无法区分"网络抖动"和"服务器重启"，重连后需要自行决定是否全量刷新状态。

**建议修复：**
在 `connection.ready` 事件 payload 中增加 `server_restart` 标志或 `server_start_time`，客户端据此决定是否全量刷新。

---

## 修复依赖关系图

```
DEF-RT-001 (Desktop 多播)
    ├──→ DEF-RT-004 (Desktop friend.request)
    ├──→ DEF-RT-005 (Desktop presence)
    └──→ DEF-RT-008 (Desktop message 音效)

DEF-RT-006 (Desktop SoundService)
    └──→ DEF-RT-008 (Desktop message 音效)

DEF-RT-002 (本地后端同步)
    └──→ 所有后端功能的可测试性

DEF-RT-003 (Logout 断开 WS)
    └──→ 独立修复，无依赖

DEF-RT-007 (Desktop EventEnvelope 类型安全)
    └──→ 独立修复，无依赖
```

---

## 建议修复顺序

### 第一批（P0，必须先修）
1. **DEF-RT-002** — 同步本地后端代码（基础，不然后续无法测试）
2. **DEF-RT-001** — Desktop 多播改造（Desktop 所有实时功能的前置）
3. **DEF-RT-003** — Logout 断开 WS（安全 + 资源，双端独立修复）

### 第二批（P1，依赖 P0）
4. **DEF-RT-007** — Desktop EventEnvelope 类型安全（独立）
5. **DEF-RT-004** — Desktop friend.request.created（依赖 001）
6. **DEF-RT-005** — Desktop presence.update（依赖 001 + 002）
7. **DEF-RT-006** — Desktop SoundService（独立）
8. **DEF-RT-008** — Desktop message 音效（依赖 001 + 006）

### 第三批（P2，增强）
9. DEF-RT-009 — 后端定时清理
10. DEF-RT-010 — 离线恢复
11. DEF-RT-011 — 同设备策略确认
12. DEF-RT-012 — 重启引导事件

---

## 当前 Gate 状态

```
REALTIME CORE GATE = NOT PASS

阻断项（P0）：3 个未修复
  - DEF-RT-001: Desktop on_event 单播
  - DEF-RT-002: 本地后端不同步
  - DEF-RT-003: Logout 不断开 WS

重要项（P1）：5 个未修复
增强项（P2）：4 个未修复

等待授权进入 IMPLEMENTATION 阶段。
```

---

*报告生成时间：2026-08-25*
*基于：全仓 READ-ONLY RECON，未修改任何代码*
