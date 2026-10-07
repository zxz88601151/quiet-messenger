# 状态机与规则（V1 冻结）

---

## 1. FriendRequest 状态机
```
        (A 添加 B)
            │
            ▼
        pending ──────────────┐
            │                 │
   POST accept                │ POST reject
            │                 │
            ▼                 ▼
        accepted           rejected
            │
   建立双向 Friendship
   预创建 Conversation
```
- 同一 (sender, receiver) 已 pending/accepted → 拒绝重复创建（返回既有）。
- 反向已 accepted → 视为已是好友，提示。
- pending 可转 accepted/rejected，终态不可逆（rejected 不自动转回）。

## 2. Friendship 规则
- 接受请求时双向写入 (A→B, B→A)，UNIQUE(user_id, friend_id) 防重。
- 删除好友：移除双向 Friendship（保留 Message）。
- 删除后发消息：校验 Friendship 缺失 → 403 FRIEND_REQUIRED。

## 3. Conversation 规则
- 创建时 user_a=min(id1,id2), user_b=max(id1,id2)，UNIQUE(user_a,user_b) 去重。
- 仅好友可创建/访问；越权访问 → 403。
- 一对用户唯一会话，杜绝 A-B 多份。

## 4. Message 状态机（客户端展示，V1.1 修订）
```
sending ──(服务端201/WS message.created)──▶ sent ──(对端 message.read)──▶ read
   │                                            │
   │ 失败(网络超时/服务端错误/鉴权失败)          │ (V1.1 不实现撤回/编辑)
   ▼                                            ▼
failed ──(用户手动点击重发)──▶ sending      (终态)
```
- **sending**：客户端本地乐观态。消息已从客户端发出，等待服务端确认。不持久化（内存中），页面刷新可丢失。
- **sent**：服务端确认持久化（REST 201 或 WS message.created）。依据：Message 记录已存在，read_at = NULL。
- **read**：收到 `message.read` WS 事件，且双方 `read_receipt_enabled` 均为 true。依据：read_at != NULL + 隐私设置检查。
- **failed**：客户端本地态。发送失败（网络超时 >10s / 服务端返回错误 / 鉴权失败）。不持久化（内存中），页面刷新可丢失。用户手动点击「重发」后回到 sending。
- **V1.1 不实现**：撤回 / 编辑 / 删除 / 引用 / @ / 回复 / 反应 / delivered / queued / pending_server / waiting_ack / uploading。
- **服务端不存储 status 字段**。sending / failed 为客户端本地态，服务端 Message 表仅通过 read_at 判断已读。详见 `DATA_MODEL.md` Message 状态说明。

### Message 状态 UI 展示规范（V1.1 冻结）

| 状态 | 气泡样式 | 状态图标 | 文字提示 | 动画 |
|---|---|---|---|---|
| **sending** | 正常气泡（发送方颜色），半透明 | 旋转 spinner（小） | 无 | spinner 旋转，克制不抢眼 |
| **sent** | 正常气泡，完全不透明 | 单勾（灰色） | 无 | 无 |
| **read** | 正常气泡，完全不透明 | 双勾（蓝色 / accent 色） | 无 | 无 |
| **failed** | 正常气泡，完全不透明 | 红色感叹号 ⚠️ | 「发送失败 · 点击重发」 | 无，点击气泡触发重发 |
| **waiting_network** | 灰色气泡（低饱和度），半透明 | 时钟图标 🕐 | 「等待网络」 | 无，网络恢复后顶部提示手动重发 |

**UI 原则**：
- 状态图标位于气泡右下角，尺寸小（12-14px），不抢占消息内容。
- 不使用大型动画或闪烁效果。
- failed 状态的红色仅用于感叹号图标，不改变气泡整体颜色（避免视觉噪音）。
- waiting_network 状态的灰色气泡明确区分于正常消息，用户一眼可知「这条还没发出去」。
- 网络恢复后，waiting_network 消息不自动变为 sending，必须用户手动点击顶部「重发」按钮或点击气泡触发。

### 离线发送状态（V1.1 新增，客户端本地态）
```
[网络断开]
   │
   ▼
用户输入 → 点击发送 → waiting_network
   │
   │ [网络恢复]
   ▼
顶部提示「有 N 条消息待发送 · 重发」
   │
   │ [用户手动点击重发]
   ▼
waiting_network → sending → sent
```
- `waiting_network`：客户端内存临时态，不持久化。页面刷新后可以丢失。
- 网络恢复后**不得自动发送**，必须由用户手动触发重发。
- V1.1 不实现：自动重试、持久化离线队列、页面刷新恢复、后台自动重试。完整离线队列进入 V1.5。
- 详见 `WS_PROTOCOL.md` 离线发送章节。

## 5. QR Login 状态机（V1 核心）
```
WAITING ──(手机 scan)──▶ SCANNED ──(手机 confirm)──▶ CONFIRMED ──(服务端授权)──▶ AUTHORIZED
   │                        │                            │
   │ 过期(expire)           │ 过期                        │ 过期
   ▼                        ▼                            ▼
EXPIRED                  EXPIRED                     EXPIRED
   │                        │
   │ 手机 cancel            │ 手机 cancel
   ▼                        ▼
CANCELLED              CANCELLED
   │
   │ 重复 scan/confirm 已使用
   ▼
REJECTED (二维码已使用，拒绝重放)
```
- 生命周期 90s（冻结）。
- 一次性：CONFIRMED/AUTHORIZED/CANCELLED/EXPIRED 后 nonce 失效，重放返回 QR_USED。
- **安全边界分离（冻结）**：`status` 轮询**只返回状态枚举**，AUTHORIZED 时仅附带一次性 `auth_code`；token 由独立 `POST /auth/desktop/qr/exchange` 用 auth_code 兑换；**获得正式 token 后才建立已鉴权 WebSocket**。
- 桌面端轮询参数（冻结）：间隔 2–3s；终态（AUTHORIZED/EXPIRED/CANCELLED/REJECTED）立即停止轮询；网络异常有限重试 + UI 提示；不使用未鉴权 WS。

## 6. Device / Token 生命周期
- 登录 → 建 Device + 发 RefreshToken（绑定 device）。
- Refresh → 轮换（旧吊销，新签发）。
- 退出 / 移除设备 → RefreshToken.revoked + Device.revoked_at + WS `device.revoked`。
- 桌面端持久化 RefreshToken（安全存储），重启走 `/auth/refresh` 自动登录，无需每次扫码。

---

## 7. Typing 状态机（V1.1 新增，客户端 + WS）

```
idle ──(用户开始输入)──▶ active ──(停止输入 1500ms)──▶ idle
  ▲                          │
  │                          │ (继续输入，重置计时器)
  └──────────────────────────┘
  │
  │ (离开聊天页 / 发送消息 / 切换会话)
  ▼
idle（立即发送 typing.stop）
```

### 客户端行为
- **idle → active**：用户在输入框输入第一个字符时，发送 `typing.start` WS 事件。
- **active 持续输入**：不重复发送 `typing.start`。每次按键重置 1500ms 计时器。
- **active → idle**：停止输入 1500ms 后，发送 `typing.stop` WS 事件。
- **立即 idle**：离开聊天页面、发送消息、切换会话时，立即发送 `typing.stop`，不等待 1500ms。
- **不得按照每次键盘输入发送** typing.start。

### 服务端转发规则
- 服务端收到 `typing.start` / `typing.stop` 后，检查会话双方的 `privacy_settings.typing_indicator_enabled`。
- **双方均为 true** → 向对端转发 `typing.start` / `typing.stop`。
- **任一方为 false** → 不转发（严格对等原则，与已读回执一致）。

### 对端 UI 行为
- 收到 `typing.start` → 聊天窗口显示「XXX 正在输入…」轻量提示（三点动画）。
- 收到 `typing.stop` → 隐藏「正在输入」提示。
- 对端 UI 不得因为 typing 事件而产生通知/声音/震动。

---

## 8. Now 状态（V1.1 修订，精简）

### V1.1 最终状态集

| 状态 | 类型 | 用户可手动设置 | 视觉 | 行为 |
|---|---|---|---|---|
| **Online** | 用户手动状态（默认） | ✅ | 绿点 | 正常接收通知和声音 |
| **Do Not Disturb** | 用户手动状态 | ✅ | 红点 / 月亮图标 | 仍然接收消息，消息正常进入 Chat，但不产生普通通知 / 声音 / 震动 |
| **Offline** | 系统自动状态 | ❌ | 灰点 | 断网 / 退出登录后自动变为 Offline，用户不可手动设置 |

### V1.1 删除的状态
- **Busy**（忙碌）—— 与 Do Not Disturb 语义重叠，删除。
- **Focus**（专注）—— 生产力工具状态，私人通讯不需要，删除。
- **Away**（离开）—— 由系统自动判断（5 分钟无操作），不需要用户手动设置，V1.1 不单独展示。

### 状态流转
```
Online ──(用户手动切换)──▶ Do Not Disturb
  ▲                              │
  └────(用户手动切换)────────────┘

[系统检测到断网/退出]
   │
   ▼
Offline（系统态，覆盖用户手动态）
   │
   │ [网络恢复/重新登录]
   ▼
回到用户上次设置的手动态（Online 或 Do Not Disturb）
```

### 约束
- Now 状态与 `online_status_visibility` 保持概念独立。Do Not Disturb 是通知行为设置，Online/Offline 是在线状态展示。
- 用户设置为 Do Not Disturb 时，好友仍可看到该用户在线（绿点），但消息不触发通知。
- `online_status_visibility = "none"` 时，好友看到该用户始终为 Offline（灰点），即使用户实际为 Online。
- Now 状态不向好友广播为独立事件，仅影响本地通知行为和头像状态点。

### 在线状态展示规则（V1.1 冻结）
- **好友之间仅展示 Online / Offline 两种状态**（绿点 / 灰点）。
- **禁止**好友之间展示 Last Seen / Last Active / "15 分钟前" / "1 小时前" 等最后活跃时间。
- 在线状态只负责"当前是否在线"，不承担社交追踪功能。
- **例外**：Devices 页面可以展示用户自己的设备 `last_active_at`（这是设备安全信息，用于用户判断是否有异常登录，不属于好友在线状态展示）。
- `online_status_visibility = "none"` 时，好友看到该用户始终为 Offline，不展示任何时间信息。

---

## 9. Local Retention 规则（V1.1 新增，客户端本地）

### 核心规则
1. 用户的 `privacy_settings.message_retention` 仅控制**当前设备的本地历史**，不影响云端和其他设备。
2. 本地删除的消息**不会因为普通同步再次自动出现**。
3. 客户端必须为每个会话记录 `local_history_cutoff`（TIMESTAMP），普通同步不得主动获取 cutoff 之前的历史消息。
4. 只有用户明确执行「加载更早消息」时，才允许主动请求更早历史。
5. 即使用户主动加载，加载后的消息仍然受当前本地 retention policy 管理——下次启动时超过保留时长的消息仍会被本地清理，并更新 cutoff。
6. **禁止**：local delete → automatic sync → message resurrection（本地删除后因普通同步自动恢复）。

### 行为定义

| 操作 | 本地行为 | 云端行为 | 同步行为 |
|---|---|---|---|
| message_retention = forever | 保留所有本地消息 | 不变 | 新消息正常同步 |
| message_retention = 30_days / 1_year | 超过时长的本地消息被清理，更新 local_history_cutoff | 不变 | 普通同步不拉取 cutoff 之前的消息 |
| clear_local_messages（一次性） | 所有会话本地历史清空，cutoff 更新为当前时间 | 不变 | 新消息正常接收，不自动拉取历史 |
| 用户手动「加载更早消息」 | 拉取 cutoff 之前的消息并展示 | 不变 | 下次启动仍受 retention policy 管理 |

### 与新设备首次同步的关系
- 新设备登录时的首次全量同步：拉取全部历史（不受旧设备 cutoff 影响），然后应用新设备自己的 retention policy。
- 这是唯一的例外场景——新设备没有历史 cutoff，首次同步属于初始化，不是「普通同步自动恢复」。

---

## V1.1 状态机修订记录

| 修订项 | 类型 | 说明 |
|---|---|---|
| Message 状态机 | 修订 | 增加 failed 分支（sending → failed → sending）。明确 sending/failed 为客户端本地态，服务端不存 status。 |
| 离线发送状态 | 新增 | waiting_network 为内存临时态，恢复后手动重发，不自动发送，刷新可丢失。 |
| Typing 状态机 | 新增 | idle ↔ active，1500ms 停止判定，服务端按隐私设置对等转发。 |
| Now 状态 | 修订 | 精简为 Online / Do Not Disturb（手动）+ Offline（系统）。删除 Busy / Focus / Away（手动）。 |
| Local Retention | 新增 | local_history_cutoff 防止本地删除后自动同步恢复。 |

**V1.1 状态机原则**：服务端状态保持精简（Message 仅 read_at），客户端负责本地展示状态（sending / failed / waiting_network / sync_status）。不因为 UI 展示需要而向服务端增加临时状态字段。
