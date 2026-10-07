# 共享数据模型（V1 冻结）— 双端唯一事实源（手机 Flutter + 电脑 PySide6）

> 任何一端（Backend / Flutter / PySide6）的模型映射必须以本文件为准。
> 字段命名使用 snake_case（后端/DB），客户端映射为本平台惯例（Dart camelCase / Python snake_case）。

---

## 1. User（账号）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID (PK) | | 服务端生成 |
| username | VARCHAR(32) | UNIQUE, NOT NULL | 不可改（注册后冻结） |
| phone | VARCHAR(20) | UNIQUE, NOT NULL | 不可改 |
| password_hash | VARCHAR(255) | NOT NULL | bcrypt，绝不明文 |
| nickname | VARCHAR(32) | NOT NULL | 可改 |
| avatar | VARCHAR(512) NULL | | 可改；V1 用默认头像 + 上传路径，不做图床 |
| bio | TEXT NULL | | 可改（蓝图未强制但保留，V1 可空） |
| privacy_settings | JSON | NOT NULL, DEFAULT '{}' | V1.1 新增。用户隐私与偏好设置，结构见下方「Privacy Settings 结构」。服务端持久化，客户端拉取后本地缓存。 |
| created_at | TIMESTAMP | | server |
| updated_at | TIMESTAMP | | server |

**不可改字段**：username、phone（除非后续产品明确要求）。

### Privacy Settings 结构（V1.1 冻结）

`privacy_settings` 为 JSON 字段，包含以下键。缺失键时使用默认值。

| 键 | 类型 | 允许值 | 默认值 | 说明 |
|---|---|---|---|---|
| read_receipt_enabled | BOOLEAN | true / false | true | 已读回执开关。关闭后采用严格对等原则：对方看不到该用户的已读状态，该用户也看不到对方的已读状态。 |
| online_status_visibility | ENUM (string) | "all" / "none" | "all" | 在线状态可见性。V1.1 仅支持两档，不支持「部分好友可见」。设为 "none" 时，好友看到该用户始终为离线，且不显示 Last Seen / Last Active。 |
| typing_indicator_enabled | BOOLEAN | true / false | true | 正在输入指示器开关。关闭后采用严格对等原则：对方看不到该用户的正在输入，该用户也看不到对方的正在输入。 |
| new_device_login_alert | BOOLEAN | true / false | true | 新设备登录提醒开关。开启后，有新设备登录该账号时，通过应用内消息和系统通知提醒用户。**唯一设置源**：Devices 页面显示真实开关，Privacy 页面仅显示跳转链接，不重复设置。 |
| message_retention | ENUM (string) | "forever" / "30_days" / "1_year" | "forever" | 本地消息保留时长。仅控制当前设备的本地历史，不影响云端和其他设备。超过时长的本地消息由客户端清理，且不会因普通同步自动恢复。 |

**约束**：
- `online_status_visibility` 不允许 "some_friends" / "whitelist" / "blacklist" 等值，V1.1 仅 "all" / "none"。
- `message_retention` 不允许自定义天数，仅三档。
- 所有布尔键缺失时默认为 true（偏向功能开启，但用户可自主关闭）。
- `privacy_settings` 的修改通过 `PATCH /users/me` 提交，服务端合并更新（merge patch），不覆盖整个 JSON。

### Privacy Settings 字段读写与同步规范（V1.1 冻结）

| 字段 | 谁写 | 谁读 | 是否持久化 | 是否同步 | 隐私影响 |
|---|---|---|---|---|---|
| read_receipt_enabled | 用户通过 PATCH /users/me 写入；服务端合并更新 | 客户端读取后本地缓存，用于 UI 展示已读状态；服务端在广播 message.read 前读取检查 | ✅ 服务端 JSON 字段持久化 | ✅ 多设备同步，任一设备修改后其他设备通过 GET /users/me 拉取更新 | 关闭后双方均不可见已读状态（严格对等） |
| online_status_visibility | 用户通过 PATCH /users/me 写入 | 客户端读取后决定是否展示自己的在线状态；服务端在向好友推送在线状态时读取检查 | ✅ 持久化 | ✅ 多设备同步 | 设为 "none" 时好友看到该用户始终为离线 |
| typing_indicator_enabled | 用户通过 PATCH /users/me 写入 | 客户端读取后决定是否展示正在输入；服务端在转发 typing 事件前读取检查 | ✅ 持久化 | ✅ 多设备同步 | 关闭后双方均不可见正在输入（严格对等） |
| new_device_login_alert | 用户通过 PATCH /users/me 写入；真实 UI 开关在 Devices → Security | 客户端读取后决定是否展示新设备登录提醒；服务端在新设备登录时读取检查，决定是否发送提醒 | ✅ 持久化 | ✅ 多设备同步 | 唯一设置源，Privacy 页面仅显示跳转链接，不重复设置 |
| message_retention | 用户通过 PATCH /users/me 写入 | 客户端读取后执行本地消息保留策略（清理超过时长的本地消息）；服务端不执行消息删除 | ✅ 持久化 | ✅ 多设备同步，但每台设备独立执行本地保留策略 | 仅控制当前设备本地历史，不影响云端和其他设备 |

**重要**：
- `privacy_settings` 是 User 模型的子字段，不是独立表。所有 5 个键共享同一个 JSON 字段。
- 修改采用 merge patch：仅更新提交的键，未提交的键保持不变。
- 客户端应在登录时通过 GET /users/me 拉取完整的 privacy_settings，本地缓存。修改后通过 PATCH /users/me 提交，成功后更新本地缓存。
- 服务端在广播 message.read / typing 事件时，必须实时读取双方的 privacy_settings（或使用缓存，但缓存更新延迟不得超过 5 秒）。

---

## 2. Device（设备，V1 核心新增）

User 与 Device 必须分离。一个 User 可拥有多个 Device。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID (PK) | | |
| user_id | UUID FK → User | NOT NULL | |
| device_type | ENUM('mobile','desktop') | NOT NULL | |
| device_name | VARCHAR(64) | | 如 "Windows PC" / "iPhone 15" |
| device_identifier | VARCHAR(255) | | 平台稳定标识（非永久 Token） |
| last_active_at | TIMESTAMP NULL | | |
| created_at | TIMESTAMP | | |
| revoked_at | TIMESTAMP NULL | | 撤销后失效 |

**索引**：UNIQUE(user_id, device_identifier) 防重复登记。

### Device 同步状态说明（V1.1 新增，客户端概念）

**服务端 Device 表不存储 sync_status 字段。** 设备的同步状态由客户端本地推导，用于 Devices 页面展示。

| 客户端状态 | 含义 | 推导依据 |
|---|---|---|
| synced | 该设备消息已同步到最新 | 客户端本地最后一条消息时间 ≥ 服务端会话 updated_at，且 WS 连接正常 |
| syncing | 该设备正在拉取历史消息 / 实时同步中 | 客户端正在执行 REST 增量拉取，或 WS 连接刚建立正在追平 |
| pending | 该设备离线，有未同步的消息 | 设备 last_active_at 较旧，或服务端有该设备未确认的消息 |

**重要**：`online`（设备在线）不等同于 `synced`（已同步）。设备在线但正在同步是合法状态，Devices 页面必须分别展示在线状态和同步状态，不得合并。

---

## 3. RefreshToken（刷新令牌，按设备维度）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID (PK) | | |
| user_id | UUID FK | NOT NULL | |
| device_id | UUID FK → Device | NOT NULL | 令牌绑定设备 |
| token_hash | VARCHAR(255) | UNIQUE NOT NULL | 只存哈希 |
| expires_at | TIMESTAMP | NOT NULL | |
| revoked | BOOLEAN | DEFAULT false | 可吊销（退出/移除设备） |
| created_at | TIMESTAMP | | |

**轮换策略**：refresh 时签发新令牌、吊销旧令牌（Rotation），降低泄露面。

---

## 4. QRLoginSession（扫码登录会话，V1 核心）

二维码**绝不**包含密码或长期 Token，只含一次性短生命周期 session。

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID (PK) | | session_id |
| nonce | VARCHAR(64) UNIQUE | NOT NULL | 防重放 |
| status | ENUM('WAITING','SCANNED','CONFIRMED','AUTHORIZED','EXPIRED','CANCELLED','REJECTED') | DEFAULT 'WAITING' | 状态机见下 |
| device_id | UUID FK NULL | | 电脑端设备（create 时预建或绑定） |
| user_id | UUID FK NULL | | 手机确认后绑定 |
| expires_at | TIMESTAMP | NOT NULL | 60~120s 生命周期 |
| created_at | TIMESTAMP | | |
| confirmed_at | TIMESTAMP NULL | | |
| authorized_at | TIMESTAMP NULL | | |

**二维码内容**：`chatapp://login?session=<id>&nonce=<nonce>`（手机解析后调 `/auth/desktop/qr/scan`）。

---

## 5. FriendRequest（好友请求）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID (PK) | | |
| sender_id | UUID FK | NOT NULL | |
| receiver_id | UUID FK | NOT NULL | |
| status | ENUM('pending','accepted','rejected') | DEFAULT 'pending' | |
| created_at | TIMESTAMP | | |
| updated_at | TIMESTAMP | | |

**唯一约束**：UNIQUE(sender_id, receiver_id) —— 防止重复请求（同一方向）。
**业务规则**：已存在 pending/accepted 时不重复创建；反向已存在 accepted 则视为已是好友。

---

## 6. Friendship（好友关系）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID (PK) | | |
| user_id | UUID FK | NOT NULL | |
| friend_id | UUID FK | NOT NULL | |
| created_at | TIMESTAMP | | |

**唯一约束**：UNIQUE(user_id, friend_id) —— 防重复好友。
**写入规则**：接受请求时**双向**写入 (A→B) 与 (B→A)，查询时按 user_id 取即可。

---

## 7. Conversation（一对一会话）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID (PK) | | |
| user_a | UUID FK | NOT NULL | 规范化：user_a = min(u1,u2) |
| user_b | UUID FK | NOT NULL | user_b = max(u1,u2) |
| created_at | TIMESTAMP | | |
| updated_at | TIMESTAMP | | |

**唯一约束**：UNIQUE(user_a, user_b) —— 一对用户仅一个会话，杜绝 A-B / A-B / A-B 重复。
**创建规则**：服务端按 min/max 规范化后 upsert；好友关系前置校验。

---

## 8. Message（文字消息）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | UUID (PK) | | server 生成 |
| conversation_id | UUID FK | NOT NULL | |
| sender_id | UUID FK | NOT NULL | |
| client_message_id | VARCHAR(64) | | **防网络重试重复**（客户端生成，唯一）。V1.1 继续承担幂等与防重复发送职责。 |
| content | TEXT | NOT NULL | text only |
| created_at | TIMESTAMP | | server 生成 |
| read_at | TIMESTAMP NULL | | 接收方读取时填。用于已读回执。 |

**去重**：UNIQUE(conversation_id, client_message_id) 防止重试产生重复消息。
**类型**：V1 仅 `text`，预留 type 字段非必须（蓝图未要求，不提前扩展）。

### Message 状态说明（V1.1 冻结）

**服务端 Message 表不存储 status 字段。** 消息展示状态由客户端本地维护，服务端仅通过 `read_at` 判断是否已读。

| 客户端状态 | 含义 | 服务端依据 | 持久化 |
|---|---|---|---|
| sending | 消息已从客户端发出，等待服务端 201 确认 | 无（本地乐观态） | 不持久化（内存中） |
| sent | 服务端已确认持久化（REST 201 或 WS message.created） | Message 记录已存在，read_at = NULL | 由服务端记录推导 |
| read | 对方已读取 | read_at != NULL，且对方未关闭已读回执 | 由服务端记录 + 隐私设置推导 |
| failed | 发送失败（网络超时 / 服务端错误 / 鉴权失败） | 无（本地态） | 不持久化（内存中，页面刷新可丢失） |

**状态流转**：详见 `STATE_MACHINES.md` 第 4 节。

**V1.1 禁止新增的服务端字段**：`status`、`delivered`、`queued`、`pending_server`、`waiting_ack`、`uploading`。这些均为客户端本地态或未来架构评审项，V1.1 不进入服务端模型。

### 离线发送（V1.1 冻结）

V1.1 **不实现完整离线发送队列**。详见 `STATE_MACHINES.md` 第 5 节。

- 网络断开时用户仍可输入，点击发送后消息进入 `waiting_network`（本地临时态，内存中，不持久化）。
- 网络恢复后由用户**手动**触发重发，不自动重试。
- 页面刷新后 `waiting_network` 可以丢失。
- 完整离线队列（自动重试、持久化、刷新恢复）进入 V1.5。

---

## 9. LocalRetention（本地消息保留，V1.1 新增，客户端概念）

> 这是**客户端本地存储概念**，不是服务端表。服务端不存储 LocalRetention 记录。每个客户端独立维护自己的本地保留策略。

### 背景

用户的 `privacy_settings.message_retention` 控制本地消息保留时长。为防止「本地删除 → 普通同步 → 消息自动恢复」的矛盾，客户端必须记录每个会话的本地历史截断点。

### 客户端本地记录结构

| 字段 | 类型 | 说明 |
|---|---|---|
| conversation_id | UUID | 会话 ID |
| local_history_cutoff | TIMESTAMP NULL | 本地历史截断时间点。该时间点之前的消息不会因普通同步自动拉取。NULL 表示无截断（永久保留）。 |

### 核心规则（V1.1 冻结）

1. **普通同步不得主动获取 cutoff 之前的历史消息**。客户端增量拉取消息时，请求参数必须 ≥ local_history_cutoff。
2. **只有用户明确执行「加载更早消息」时**，才允许主动请求 cutoff 之前的历史。
3. **即使用户主动加载**，加载后的消息仍然受当前本地 retention policy 管理——下次启动时，超过保留时长的消息仍会被本地清理，并更新 cutoff。
4. **禁止**：local delete → automatic sync → message resurrection（本地删除后因普通同步自动恢复）。
5. `clear_local_messages`（一次性操作）执行后，所有会话的 `local_history_cutoff` 更新为当前时间，本地历史清空。新消息正常接收。

### 与云端的关系

- 云端消息历史独立于本地保留策略，不受影响。
- 其他设备的本地保留策略独立，不受本设备设置影响。
- 新设备登录时的首次全量同步：拉取全部历史（不受旧设备 cutoff 影响），然后应用新设备自己的 retention policy。

---

## 关系总览

```
User 1───* Device
User 1───* RefreshToken (via Device)
User 1───* FriendRequest (sender/receiver)
User 1───* Friendship
User 1───* Conversation (user_a/user_b)
User 1───* Message (sender)
QRLoginSession ──* Device (desktop) / User (mobile)
```

## 客户端模型映射约定

- **Flutter**：Dart 类，字段 camelCase，使用 `json_serializable` 或手写 fromJson。
- **PySide6**：Python dataclass，字段 snake_case，httpx 反序列化。
- **共享 key**：JSON 序列化统一 snake_case（后端吐什么，两端就解析什么），避免双端命名漂移。

---

## V1.1 架构修订记录

| 修订项 | 类型 | 说明 |
|---|---|---|
| User.privacy_settings | 新增字段 | JSON 字段，包含 5 个隐私偏好键（read_receipt_enabled / online_status_visibility / typing_indicator_enabled / new_device_login_alert / message_retention） |
| Message 状态说明 | 新增章节 | 明确 sending/failed 为客户端本地态，服务端不存储 status 字段；状态流转见 STATE_MACHINES.md |
| 离线发送说明 | 新增章节 | V1.1 不实现完整离线队列，waiting_network 为内存临时态，手动重发，刷新可丢失 |
| LocalRetention | 新增概念 | 客户端本地记录 conversation_id + local_history_cutoff，防止本地删除后自动同步恢复 |
| Device 同步状态 | 新增说明 | sync_status 为客户端推导态（synced/syncing/pending），服务端不存储；online ≠ synced |
| Message 服务端字段 | 冻结 | 禁止新增 status / delivered / queued / pending_server / waiting_ack / uploading |

**V1.1 数据模型原则**：服务端模型保持精简，客户端负责本地状态（sending/failed/waiting_network/sync_status/local_history_cutoff）。不因为 UI 展示需要而向服务端模型增加临时状态字段。
