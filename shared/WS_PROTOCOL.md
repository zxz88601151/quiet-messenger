# 共享 WebSocket 协议（V1 冻结）— 双端唯一事实源（手机 Flutter + 电脑 PySide6）

> **端点**：`WS /ws/v1`（与 Flutter `RealtimeClient.wsPath` 一致）。
> **鉴权**：连接使用 **`Authorization: Bearer <access_token>` 请求头**（不放入 URL，不首帧 `auth`）。
>   无效 / 过期 token → 服务端以 **关闭码 4401** 断开（非 1008）。
> **帧格式**：JSON `{ "type": "...", "id": "<event_id>", "timestamp": "<iso8601>", "payload": {...} }`
>   （与 Flutter `EventEnvelope` 字段一致：`type` / `id` / `timestamp` / `payload`）。
> **设计原则**：WS 只负责实时性，可靠性由 DB 兜底（离线消息靠 REST 拉取）。
>
> ⚠️ 文档修订记录：本节于 V1.1 FLUTTER RECOVERY 阶段修正 —— 原文档写的是
> `/ws` + `?token=` + 关闭码 1008 + `{type,payload,ts}`，与真实实现不符，已对齐。

---

## 1. 客户端 → 服务端（上行）

### auth
```json
{ "type":"auth", "payload":{ "token":"<access_token>" } }
```
连接后首帧；成功后服务端回 `auth.ok`，失败回 `error` 并关闭。

### message.send
```json
{ "type":"message.send", "payload":{
  "conversation_id":"", "content":"", "client_message_id":""
}}
```
服务端持久化 → 广播 `message.created` 给会话双方在线设备。

### message.read
```json
{ "type":"message.read", "payload":{
  "conversation_id":"", "last_read_message_id":""
}}
```
标记该会话中 ≤ last_read 的消息 read_at；广播 `message.read` 给对端。

### heartbeat（ping/pong）
每 25s 客户端发 `{ "type":"ping" }`，服务端回 `{ "type":"pong" }`；超时（>2 周期）断开。

### typing.start / typing.stop（V1.1 新增）
```json
// typing.start
{ "type":"typing.start", "payload":{ "conversation_id":"" } }

// typing.stop
{ "type":"typing.stop", "payload":{ "conversation_id":"" } }
```
客户端向服务端报告正在输入状态。**不得按照每次键盘输入发送**，协议语义：
- 第一次开始输入：发送 `typing.start`
- 持续输入：不重复发送 `start`
- 停止输入约 1500ms：发送 `typing.stop`
- 如果停止后继续输入：重新发送 `typing.start`（重新进入 active 状态）
- 离开聊天页面 / 发送消息后：立即发送 `typing.stop`

服务端收到后，检查接收方的 `privacy_settings.typing_indicator_enabled` 和发送方的 `privacy_settings.typing_indicator_enabled`，**双方均开启时才向接收方转发** `typing.start` / `typing.stop`。任一方关闭则不转发（严格对等原则）。

**完整规范（V1.1 冻结）**：

| 规范项 | 说明 |
|---|---|
| **Direction** | 上行：客户端 → 服务端；下行：服务端 → 对端客户端 |
| **Authentication** | WS 连接必须已通过 Bearer token 鉴权（连接请求头 `Authorization: Bearer <access_token>`，不使用 URL query 参数）。未鉴权连接收到 typing 事件直接忽略并关闭。 |
| **Payload** | 上行：`{ conversation_id }`；下行：`{ conversation_id, user_id }`。**不得**发送输入框内容、字符数量、用户输入文本。 |
| **Validation** | 1. 验证身份：WS 连接已鉴权，user_id 从连接上下文获取；2. 验证 conversation membership：发送方必须是该会话的合法成员，否则忽略；3. 检查 privacy setting：服务端在转发前检查双方 `typing_indicator_enabled`。 |
| **Broadcast** | 仅向同一会话的对端在线设备转发。不向发送方自己的其他设备转发（typing 是会话级实时状态，不是账号级状态）。 |
| **Persistence** | **不持久化**。typing event 不进入 Message 表，不写入数据库，不参与历史同步，不属于消息历史的一部分。只属于实时状态。 |
| **Reconnect Behavior** | 连接断开后，typing 状态自动失效。客户端重连后不恢复之前的 typing 状态（不自动重发 typing.start）。对端在连接断开后应清除该用户的 typing 指示器。客户端应具有超时保护：即使未收到 typing.stop，超过 30s 也自动清除 typing 指示器。 |
| **Rate Limit** | 服务端可对 typing 事件做频率限制（如每会话每用户每秒最多 1 个 typing 事件），防止恶意客户端刷屏。 |

---

## 2. 服务端 → 客户端（下行）

### auth.ok
`{ "type":"auth.ok", "payload":{ "user_id":"" } }`

### message.created
```json
{ "type":"message.created", "payload":{ ...Message, "conversation_id":"" } }
```
实时新消息。接收方 UI 插入；若当前在会话内且前台，自动触发 `message.read`。

### message.read
```json
{ "type":"message.read", "payload":{ "conversation_id":"", "reader_id":"", "read_at":"" } }
```
对端已读 → 发送方 UI 更新气泡状态（已发送→已读）。

**严格对等原则（V1.1 冻结）**：服务端在广播 `message.read` 之前，必须检查会话双方的 `privacy_settings.read_receipt_enabled`：
- 双方均为 true → 正常广播 `message.read`
- 任一方为 false → **不广播** `message.read`。关闭已读回执的用户看不到对方的已读状态，对方也看不到该用户的已读状态。
- 不允许形成「我关闭了自己的已读，但还能看别人已读」的不对等行为。

### typing.start / typing.stop（V1.1 新增，下行）
```json
{ "type":"typing.start", "payload":{ "conversation_id":"", "user_id":"" } }
{ "type":"typing.stop", "payload":{ "conversation_id":"", "user_id":"" } }
```
对端正在输入 / 停止输入 → 接收方 UI 在聊天窗口显示「正在输入…」轻量提示。

**转发规则**：服务端仅在会话双方的 `privacy_settings.typing_indicator_enabled` 均为 true 时才转发。任一方关闭则不转发（严格对等原则，与已读回执一致）。

### conversation.updated
会话元数据变化（如新消息触发 updated_at / unread_count 变更）时广播，用于刷新聊天列表。

### friend.request
收到新好友请求 → 刷新请求列表。

### friend.accepted
好友关系建立 → 刷新好友列表 + 聊天列表（自动出现会话）。

### device.login
桌面端扫码授权：轮询 `GET /auth/desktop/qr/{session_id}/status` 到 AUTHORIZED（仅得一次性 `auth_code`）→ 调 `POST /auth/desktop/qr/exchange` 换取正式 Desktop Token → **获得 token 后才建立已鉴权 WebSocket**。V1 不建立未鉴权 WS。
WS 此处仅用于：授权成功后建立的已鉴权连接接收实时消息；以及设备被移除时接收 `device.revoked`。

### device.revoked
当前设备被手机端移除 → 客户端清空本地令牌、回到登录页。

### error
`{ "type":"error", "payload":{ "code":"", "message":"" } }`

---

## 3. 重连与离线策略
- 断线：客户端指数退避重连（1s → 2s → 4s … 上限 30s），重连后重新 `auth`。
- 离线消息：重连后客户端对“有未读/最后活跃时间”的会话调 `GET /conversations/{id}/messages?cursor=` 增量同步，或以 `GET /conversations` 的 `unread_count` 触发拉取。
- 不依赖 WS 存储消息：WS 断流期间消息由 REST 拉取补偿。

### 离线发送（V1.1 冻结，发送方）

V1.1 **不实现完整离线发送队列**。禁止实现：自动重试、持久化离线队列、页面刷新恢复、后台自动重试、指数退避发送队列、多设备离线事务队列。

V1.1 离线发送行为规范：

| 网络状态 | 用户输入 | 用户点击发送 | 消息状态 | UI 显示 |
|---|---|---|---|---|
| 正常（WS 在线） | 可输入 | 可发送 | sending → sent | 正常气泡 + 状态图标 |
| 断开（WS 离线） | 可输入 | 可点击 | waiting_network | 灰色气泡 + 时钟图标 + 「等待网络」文字，**不得显示「已发送」** |
| 恢复后 | — | — | waiting_network → sending → sent | 顶部提示「有 N 条消息待发送 · 重发」，由**用户手动触发**重发，**不得自动发送** |

**约束**：
- `waiting_network` 为客户端内存临时态，不持久化。页面刷新后 `waiting_network` 可以丢失。
- 网络恢复后不得自动发送 `waiting_network` 消息，必须由用户手动点击「重发」触发。
- V1.1 的离线发送属于临时发送能力，不属于持久化离线消息系统。
- 完整离线队列（自动重试、持久化、刷新恢复、多设备一致性）进入 V1.5。

## 4. 多端同步示例
```
手机发 "你好"
 → message.send
 → Backend 存 Message + read_at=null
 → 广播 message.created 给桌面端（若在线）
 → 桌面插入 "你好"，若前台自动 message.read
 → 广播 message.read 给手机
 → 手机气泡变 "已读"
```

---

## V1.1 协议修订记录

| 修订项 | 类型 | 说明 |
|---|---|---|
| typing.start / typing.stop | 新增 WS event | 上行：客户端报告正在输入状态；下行：服务端向对端广播。不得按每次按键发送，start 后 1500ms 无输入发 stop。 |
| message.read 对等原则 | 修改规则 | 服务端广播前检查双方 read_receipt_enabled，任一方关闭则不广播。禁止不对等行为。 |
| typing 转发对等原则 | 新增规则 | 与已读回执一致，双方 typing_indicator_enabled 均开启时才转发。 |
| 离线发送策略 | 新增章节 | V1.1 不实现完整离线队列。waiting_network 为内存临时态，恢复后手动重发，不自动发送，刷新可丢失。 |

**V1.1 WebSocket 协议原则**：WS 负责实时性（消息、已读、正在输入、设备事件），可靠性由服务端 DB + REST 兜底。客户端本地状态（sending / failed / waiting_network / sync_status）不进入 WS 协议，由客户端自行维护。
