# ANDROID SOUND EVENT VALIDATION REPORT

> 生成时间：2026-08-25
> 项目：V1.1 双端聊天 / Flutter Client
> APK SHA256：`E022BF5E9A82C1F829A04284BDF3D3E81A8AEB5BC428B93DDBAF5525607C49A5`

---

## 1. Audio Assets

| 音效文件 | 路径 | 大小 | 状态 |
|---------|------|------|------|
| friend_added.mp3 | `assets/sounds/friend_added.mp3` | 21,830 bytes | ✅ 已接入 |
| new_message.mp3 | `assets/sounds/new_message.mp3` | 8,231 bytes | ✅ 已接入（上一轮） |
| online.mp3 | `assets/sounds/online.mp3` | — | ❌ 不存在 |

> pubspec.yaml 已注册 friend_added.mp3 和 new_message.mp3。online.mp3 因资源不存在且无 Presence 事件链路，未注册。

---

## 2. SoundService 架构

**文件**：`lib/core/sound/sound_service.dart`

**设计原则**：
- 应用级单例（`SoundService.instance`），不重复创建 AudioPlayer
- `with WidgetsBindingObserver` 自动跟踪 App 前后台生命周期
- 业务事件 → Notifier/Event Layer → SoundService → AudioPlayer
- UI 页面禁止直接调用 AudioPlayer
- 所有 play 方法 fire-and-forget，异常静默，不影响业务逻辑

**配置项**：

| 配置 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | true | 音效总开关，Settings 未来可接入 |
| `volume` | double | 0.5 | 适中音量，非 100% |
| `foreground` | bool | true | 由 AppLifecycleState 自动更新，后台不播放 |

**方法**：

| 方法 | 音效 | 节流 | 说明 |
|------|------|------|------|
| `playFriendAdded()` | friend_added.mp3 | 3s 窗口 | 收到新 incoming pending 请求时调用，调用方需先做 ID 去重 |
| `playNewMessage()` | new_message.mp3 | 无 | MessageNotifier 已通过 message.id 去重 |
| `playOnline()` | online.mp3 | — | **空操作（BLOCKED）**，等待 Presence 事件链路 |

---

## 3. Friend Request Event（friend_added.mp3）

### 3.1 事件来源

当前项目**无 WebSocket 推送**的 friend request 事件（后端 connection_manager.py 明确写"不实现 friend.*"）。
Incoming friend request 仅通过 REST `GET /friends/requests` 轮询获取。

因此音效接入点为 **FriendNotifier.loadRequests()**，在 REST 加载完成后检测新增请求。

### 3.2 去重机制

**文件**：`lib/features/friends/friend_notifier.dart`

- `Set<String> _seenRequestIds`：记录所有已见过的请求 ID（只增不减）
- `bool _requestsInitialized`：首次加载标记

**检测逻辑 `_detectNewIncomingRequests()`**：
1. 首次加载（`_requestsInitialized == false`）：仅记录所有 ID，**不播放**（初始同步排除）
2. 后续加载：筛选 `isIncoming && status == 'pending' && !_seenRequestIds.contains(id)`
3. 存在新请求 → `SoundService.instance.playFriendAdded()`（SoundService 内部 3s 节流）
4. 更新 `_seenRequestIds`

### 3.3 节流机制

SoundService 内部 3 秒节流窗口：
- 第一次调用：立即播放，记录时间戳
- 3 秒内后续调用：忽略
- 超过 3 秒：再次播放

**效果**：2 秒内 A、C、D、E 四人同时发来请求 → 只播放 1 次 friend_added.mp3。

### 3.4 测试矩阵

| 场景 | 预期播放次数 | 验证方式 |
|------|-------------|---------|
| 首次 loadRequests（初始同步） | 0 | `_requestsInitialized` 守卫 |
| 新增 1 个 incoming pending 请求 | 1 | ID 去重 + 播放 |
| 同一 request 重复 loadRequests | 0 | `_seenRequestIds` 去重 |
| WebSocket 重连后重新加载 | 0 | ID 已在 `_seenRequestIds` |
| 重新进入 Friends 页面 | 0 | ID 已在 `_seenRequestIds` |
| 2 秒内 4 个不同新请求 | ≤1 | 3s 节流窗口 |
| 自己发送 outgoing 请求 | 0 | `isIncoming == false` 过滤 |
| 已 accepted/rejected 的请求 | 0 | `status == 'pending'` 过滤 |

> 注：当前为 REST 轮询架构，非 WebSocket 推送。音效触发依赖 loadRequests() 被调用（用户进入好友请求页面或手动刷新）。这是当前架构的固有限制，非音效层缺陷。

---

## 4. Online Event（online.mp3）— BLOCKED

### 4.1 阻塞原因

**当前项目不存在可靠的 Presence Transition Event 链路**：

| 层级 | 状态 | 说明 |
|------|------|------|
| 后端 WebSocket 事件 | ❌ 不存在 | 无 `user_online` / `user_offline` 事件，connection_manager.py 明确不实现 friend.* / presence.* |
| 后端 REST API | ❌ 不存在 | 无 GET /presence 或类似接口 |
| User 模型字段 | ❌ 不存在 | Flutter User 模型明确写"no presence fields"（Scope discipline） |
| Flutter PresenceNotifier | ❌ 不存在 | 无任何在线状态跟踪/管理组件 |
| 音频资源 | ❌ 不存在 | `assets/sounds/online.mp3` 文件不存在 |

### 4.2 明确禁止的伪造方式

以下方式均**不采用**：
- ❌ FriendsPage 打开就播放 online.mp3
- ❌ 好友列表刷新就播放
- ❌ WebSocket reconnect 就播放
- ❌ 每次收到 online 状态事件就无条件播放（事件本身不存在）
- ❌ 用初始 Presence Sync 冒充 Transition

### 4.3 解除条件

online.mp3 接入需要以下全部完成：
1. 后端实现 Presence 系统（用户上下线状态跟踪 + WebSocket `user_online`/`user_offline` 事件推送）
2. Flutter User 模型增加 presence 字段
3. Flutter 实现 PresenceNotifier（管理好友在线状态，检测 Offline→Online 真实变化）
4. 初始 Presence Sync 与 Transition 事件严格区分
5. `assets/sounds/online.mp3` 资源文件就位

**当前状态：ONLINE SOUND = BLOCKED**

---

## 5. Deduplication Summary

| 音效 | 去重依据 | 去重位置 |
|------|---------|---------|
| friend_added.mp3 | FriendRequest.id | FriendNotifier `_seenRequestIds` |
| new_message.mp3 | Message.id | MessageNotifier `_upsert()` 已有去重 |
| online.mp3 | — | BLOCKED |

---

## 6. Throttle Summary

| 音效 | 节流窗口 | 实现位置 |
|------|---------|---------|
| friend_added.mp3 | 3 秒 | SoundService `_lastFriendPlay` 时间戳比较 |
| new_message.mp3 | 无（消息频率天然较低，且 MessageNotifier 已按 ID 去重） | — |
| online.mp3 | — | BLOCKED |

---

## 7. Foreground / Background

- SoundService `with WidgetsBindingObserver`，`didChangeAppLifecycleState()` 自动更新 `_foreground`
- App 在后台（`AppLifecycleState != resumed`）：`_foreground = false`，所有 play 方法直接 return，且停止当前播放
- App 回到前台：`_foreground = true`，恢复正常播放
- 后台如需系统通知：未来走 Android Notification，不强行让 Flutter AudioPlayer 播放

---

## 8. Initial Sync 排除

| 场景 | 处理 |
|------|------|
| FriendNotifier 首次 loadRequests() | `_requestsInitialized == false` → 仅记录 ID，不播放 |
| App 启动后首次 WebSocket 连接 | （无 friend WS 事件，不适用） |
| 未来 Presence 初始同步 | （BLOCKED，待实现时需同样排除） |

---

## 9. Self Event 排除

| 场景 | 处理 |
|------|------|
| 当前用户自己发送好友请求 | `isIncoming == false` → 不触发 friend_added |
| 当前用户自己上线 | （BLOCKED，待实现时需排除 current user id） |
| 当前用户自己发消息 | MessageNotifier `msg.senderId != _currentUserId` → 不播放 new_message |

---

## 10. Rapid Events

| 场景 | 预期 |
|------|------|
| 2 秒内 4 个不同用户发来好友请求 | ≤1 次 friend_added.mp3（3s 节流） |
| 短时间多个好友上线 | （BLOCKED，待实现时需同样节流） |
| 连续多条消息 | MessageNotifier 按 message.id 去重，同一条不重复播放 |

---

## 11. Audio Failure Resilience

- 所有 `_play()` 方法包裹 `try/catch`，异常静默
- AudioPlayer 初始化失败、资源缺失、播放中断 → 不影响业务状态
- 音效失败不会导致：Crash、好友请求丢失、消息丢失、Presence 状态异常
- `enabled = false` 时业务事件正常处理，仅跳过播放

---

## 12. flutter analyze

```
30 issues found (ran in 4.7s)
```

- 全部为预存在的 info / warning（unused_import、use_build_context_synchronously、unnecessary_underscores 等）
- **0 error**
- 新增音效代码（sound_service.dart、friend_notifier.dart 修改）**零新增 analyze 问题**

---

## 13. flutter test

```
48 passed / 0 failed / 0 skipped
```

- Realtime 单元测试 36 个全部通过
- Widget 测试 12 个全部通过
- 音效代码为表现层，不影响业务逻辑测试

---

## 14. APK Build

| 项目 | 值 |
|------|-----|
| 构建模式 | release |
| 大小 | 50.43 MB |
| SHA256 | `E022BF5E9A82C1F829A04284BDF3D3E81A8AEB5BC428B93DDBAF5525607C49A5` |
| 安装状态 | Success（真机 OPPO PCPM00, 45QS8HH6R8AUS49L） |

**构建问题修复**：audioplayers_android 插件与 Kotlin 2.x + Gradle 9.x 组合触发 "Could not close incremental caches" daemon 崩溃。在 `android/gradle.properties` 中添加 `kotlin.incremental=false` 解决。

---

## 15. Remaining Limitations

1. **friend_added.mp3 依赖 REST 轮询**：当前无 WebSocket 推送，音效仅在 `loadRequests()` 被调用时触发（用户进入好友请求页或手动刷新）。未来后端实现 `friend.request.created` WebSocket 事件后可改为实时推送。
2. **online.mp3 BLOCKED**：无 Presence 系统，需后端 + Flutter 全链路实现后才能接入。
3. **音效开关未接入 Settings UI**：`SoundService.enabled` 已支持，但 Settings 页面尚未添加声音开关控件。
4. **无系统通知**：App 在后台时不播放 App 内音效，未来如需后台提醒需实现 Android Notification。

---

## 16. Final Gate

| 项目 | 状态 |
|------|------|
| friend_added.mp3 接入 | ✅ PASS（REST 轮询 + ID 去重 + 3s 节流 + 初始同步排除 + 前后台感知） |
| online.mp3 接入 | ❌ BLOCKED（无 Presence Transition Event + 无资源文件） |
| new_message.mp3 接入 | ✅ PASS（上一轮已接入，MessageNotifier ID 去重） |
| SoundService 架构 | ✅ PASS（单例 + 生命周期 + 音量 + 开关 + 异常安全） |
| flutter analyze | ✅ PASS（0 error） |
| flutter test | ✅ PASS（48/48） |
| APK Build & Install | ✅ PASS |

### 最终判定

**SOUND INTEGRATION = PASS WITH LIMITATIONS**

- friend_added.mp3 和 new_message.mp3 已正确接入，满足所有约束（去重、节流、初始同步排除、自己排除、前后台、异常安全）
- online.mp3 因无可靠 Presence 事件链路而 BLOCKED，未伪造实现
- 限制：friend_added 依赖 REST 轮询（非实时推送），online 待 Presence 系统完成

---

## 17. 修改文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `lib/core/sound/sound_service.dart` | 重写 | 增强：volume、throttle、foreground/background、online 占位、WidgetsBindingObserver |
| `lib/features/friends/friend_notifier.dart` | 修改 | 移除 sendRequest() 错误播放；新增 `_seenRequestIds`、`_requestsInitialized`、`_detectNewIncomingRequests()` |
| `pubspec.yaml` | 修改 | 注册 assets（friend_added.mp3、new_message.mp3）；添加 audioplayers: ^6.1.0 |
| `android/gradle.properties` | 修改 | 添加 `kotlin.incremental=false` 解决构建崩溃 |
| `assets/sounds/friend_added.mp3` | 新增 | 音频资源 |
| `assets/sounds/new_message.mp3` | 新增 | 音频资源 |

---

**STOP — 等待下一步授权。**
