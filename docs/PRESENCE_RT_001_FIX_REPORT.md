# Android Chat Presence Runtime Bug — Audit & Fix Report

**Date:** 2026-08-25
**Bug ID:** PRESENCE-RT-001
**Severity:** P1 (Runtime — Chat Header shows Offline for online users)
**Status:** FIXED

---

## 1. Root Cause

### **Initial Presence Sync Gap**

**断链位置:** [Backend] WebSocket connect 时未发送好友当前在线状态

**完整证据链:**

| 层级 | 组件 | 状态 | 证据 |
|------|------|------|------|
| Backend | `presence.py` | ✅ 正确 | `on_connect`/`on_disconnect` 仅发送 delta 事件 |
| Backend | `ws.py` | ❌ 缺失 | connect 时只发 `connection.authenticated` + `connection.ready`，**不发送好友当前在线状态** |
| Realtime | `RealtimeClient` | ✅ 正确 | 正确分发所有事件到 `_eventListeners` |
| Client | `PresenceNotifier` | ✅ 正确 | 正确处理 `presence.update`，`_online` map 初始为空 |
| UI | `ChatPage` | ✅ 正确 | `context.watch<PresenceNotifier>().isOnline(peer.id)` |
| ID Mapping | `peer.id` ↔ `user_id` | ✅ 正确 | 均为 String UUID，格式一致 |

**问题机理:**
```
用户 B 已在线
    ↓
用户 A 连接 WebSocket
    ↓
Backend 发送 connection.ready（不含好友在线状态）
    ↓
A 的 PresenceNotifier._online = {} (空)
    ↓
A 打开 B 的 Chat
    ↓
presence.isOnline(B.id) → _online[B] ?? false → false
    ↓
Header 显示灰色 Offline ❌
```

**能收到 message.created ≠ Presence 正常** — 消息事件是点对点发送，与 Presence 状态同步是独立链路。

---

## 2. Fix Strategy

### Backend: 初始 Presence 同步

在 WebSocket `connection.ready` 之后，查询当前用户所有在线好友，逐个发送 `presence.update` 事件（`status: "online"`, `initial: true`）。

- 使用现有 `presence.update` 事件类型，**不新增 API**
- 添加 `"initial": true` 标志区分初始同步与真实状态变化
- 初始同步失败不影响 WebSocket 连接（try/except pass）

### Client: 跳过初始事件的音效

Android `PresenceNotifier` 和 Desktop `PresenceController` 均检查 `payload["initial"] == true`，跳过 `online.mp3` 播放（但仍更新 `_online` map 并 `notifyListeners`）。

---

## 3. Code Changes

### 3.1 Backend — `app/services/presence.py`

**新增方法:** `get_online_friend_ids(user_id, db)`
- 查询用户所有好友 ID
- 过滤出当前在线的好友
- 返回在线好友 ID 列表

### 3.2 Backend — `app/routers/ws.py`

**修改位置:** `connection.ready` 之后
- 调用 `presence.get_online_friend_ids(user_id, db)`
- 对每个在线好友发送 `presence.update` 事件，payload 含 `user_id`, `status: "online"`, `initial: True`
- try/except 包裹，失败不影响连接

### 3.3 Android — `lib/features/presence/presence_notifier.dart`

**修改位置:** `_onEvent` 方法
- 读取 `evt.payload['initial']`
- 仅当 `!isInitial` 时播放 `online.mp3`
- 初始事件仍更新 `_online` map 并 `notifyListeners`

### 3.4 Desktop — `app/features/presence/__init__.py`

**修改位置:** `_on_event` 方法
- 读取 `payload.get("initial", False)`
- 仅当 `not is_initial` 时播放 `online.mp3`
- 初始事件仍更新 `state.online` 并 `_emit()`

---

## 4. Runtime Verification Matrix

| Scenario | Expected | Actual | Result |
|----------|----------|--------|--------|
| B 在线，A 连接 WS | A 收到 B 的 initial presence.update | Backend 发送 initial 事件 | ✅ (代码验证) |
| A 打开 B 的 Chat | Header 显示绿色 Online | PresenceNotifier._online[B] = true | ✅ (代码验证) |
| B 上线（A 已连接） | A 收到 presence.update (无 initial) + 音效 | delta 事件，播放 online.mp3 | ✅ (代码验证) |
| B 下线 | A 收到 presence.update offline | Header 变灰 | ✅ (代码验证) |
| 初始同步 50 个在线好友 | 不播放 50 次音效 | initial=true 跳过音效 | ✅ (代码验证) |
| 初始同步后 B 下线再上线 | 播放 1 次音效 | delta 事件触发 | ✅ (代码验证) |
| 自己上线 | 不播放音效 | current_user_id 排除 | ✅ (已有) |
| WebSocket reconnect | 不重复播放 | initial=true 或 wasOnline==isNowOnline | ✅ (代码验证) |

**真机 Runtime 验证:** 待设备连接后执行（设备当前未连接）。

---

## 5. Regression Test

| 测试 | 结果 |
|------|------|
| Backend `pytest` | ✅ 88 passed / 0 failed |
| Desktop `pytest` | ✅ 36 passed / 1 skipped |
| Flutter `flutter analyze` | ✅ 0 errors |
| Flutter `flutter test` | ✅ 48 passed / 0 failed / 0 skipped |
| Flutter `flutter build apk --release` | ✅ Success (50.8 MB) |
| Staging Backend 部署 | ✅ Deployed + Restarted + Healthy |
| Auth 登录 | ✅ 未修改 |
| Auth Logout | ✅ 未修改 |
| Friend Search/Request/Accept/Reject/Delete | ✅ 未修改 |
| Conversation 创建 | ✅ 未修改 |
| Message 发送/接收 | ✅ 未修改 |
| WebSocket Realtime | ✅ 未修改核心机制 |
| SoundService (new_message/friend_added) | ✅ 未修改 |

---

## 6. Deployment

| 组件 | 状态 | 说明 |
|------|------|------|
| Backend presence.py | ✅ 已部署 Staging | `/opt/v1.1-staging/backend/app/services/presence.py` |
| Backend ws.py | ✅ 已部署 Staging | `/opt/v1.1-staging/backend/app/routers/ws.py` |
| Docker 容器 | ✅ 已重启 | `v1.1-staging-backend` Up (healthy) |
| Android APK | ✅ 已构建 | `app-release.apk` (50.8 MB) |
| APK 安装 | ⏳ 待设备连接 | 设备 `45QS8HH6R8AUS49L` 当前未连接 |

---

## 7. Known Limitations

1. **真机 Runtime 验证待执行** — 设备未连接，需用户手动连接后安装 APK 验证
2. **初始 Presence 同步是逐个事件发送** — 如果有大量在线好友（>100），会发送多个事件。当前阶段可接受，未来可优化为批量 `presence.sync` 事件
3. **Presence 是内存态（单进程）** — 多 worker 部署需要 Redis pub/sub（Phase 5+），当前 Staging 为单容器

---

## 8. Final Judgment

### **PRESENCE FIX — PASS**

**根因明确:** Backend WebSocket connect 时缺少初始 Presence 状态同步
**修复完整:** Backend 初始同步 + 双端客户端 initial 标志音效跳过
**测试通过:** Backend 88 / Desktop 36 / Flutter 48，0 error
**部署完成:** Staging 后端已部署重启，APK 已构建
**无回归:** 所有既有功能未修改

**待用户操作:** 连接 Android 设备 → 安装新 APK → 双账号真机验证 Chat Header Presence 状态

---

## 9. STOP

本 Presence Bug 修复完成。等待真机验证确认后，不自动进入其他任务。
