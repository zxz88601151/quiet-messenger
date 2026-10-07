# 共享 API Contract（V1 冻结）— 双端唯一事实源（手机 Flutter + 电脑 PySide6）

> 基准 URL：`/api/v1`（前缀可在实现时调整，但双端必须一致）。
> 认证：除 `register` / `login` / `forgot-password` / `qr/create` / `qr/scan`(半态) 外，全部需 `Authorization: Bearer <access_token>`。

---

## 1. Auth

### POST /auth/register
```json
// request
{ "username":"", "phone":"", "password":"", "nickname":"" }
// response 201
{ "access_token":"", "refresh_token":"", "user":{...User}, "device":{...Device} }
```
注册成功后自动登录（返回 token + 移动端 device）。

### POST /auth/login
```json
// request（用户名或手机号 + 密码）
{ "identifier":"username_or_phone", "password":"", "device":{ "device_type":"mobile|desktop", "device_name":"", "device_identifier":"" } }
// response 200
{ "access_token":"", "refresh_token":"", "user":{...}, "device":{...Device} }
```

### POST /auth/refresh
```json
// request
{ "refresh_token":"" }
// response 200（轮换：旧令牌吊销，返回新令牌）
{ "access_token":"", "refresh_token":"" }
```

### POST /auth/logout
```json
// request
{ "refresh_token":"" }   // 或仅吊销当前 device
// response 200 { "ok":true }
```
退出登录：吊销当前设备 RefreshToken + 撤销 Device。

### POST /auth/forgot-password
```json
// request
{ "phone":"" }
// response 200（开发环境返回 mock 验证码；生产接短信）
{ "ok":true, "dev_code":"123456" }   // dev_code 仅 Dev 环境返回
```

### POST /auth/reset-password
```json
// request
{ "phone":"", "code":"", "new_password":"" }
// response 200 { "ok":true }
```

---

## 2. User

### PATCH /users/me
```json
// request（V1.1 修订：支持 nickname / avatar / bio / privacy_settings）
// 所有字段均可选，仅提交需要修改的字段（merge patch，不覆盖整个对象）
{
  "nickname": "",
  "avatar": "",
  "bio": "",
  "privacy_settings": {
    "read_receipt_enabled": true,
    "online_status_visibility": "all",
    "typing_indicator_enabled": true,
    "new_device_login_alert": true,
    "message_retention": "forever"
  }
}
// response 200
{ ...User, "privacy_settings": { ... } }
```

**privacy_settings 字段规范（V1.1 冻结）**：

| 字段 | 类型 | 允许值 | 默认值 | Validation |
|---|---|---|---|---|
| read_receipt_enabled | boolean | true / false | true | 非 boolean 返回 400 VALIDATION_ERROR |
| online_status_visibility | string | "all" / "none" | "all" | 其他值返回 400 VALIDATION_ERROR；V1.1 不支持 "some_friends" |
| typing_indicator_enabled | boolean | true / false | true | 非 boolean 返回 400 |
| new_device_login_alert | boolean | true / false | true | 非 boolean 返回 400 |
| message_retention | string | "forever" / "30_days" / "1_year" | "forever" | 其他值返回 400；不支持自定义天数 |

**规则**：
- `privacy_settings` 为 merge patch：仅更新提交的键，未提交的键保持不变。
- 提交 `privacy_settings: {}`（空对象）不修改任何设置。
- 缺失的键使用服务端当前值，不重置为默认值。
- 首次注册时，`privacy_settings` 初始化为全部默认值。
- `new_device_login_alert` 为**唯一设置源**：Devices 页面和 Privacy 页面均读取此字段，不得出现第二个独立字段。
- 拒绝：username / phone 修改（返回 400 或忽略，V1 默认忽略并提示不可改）。

### GET /users/me
response 200 → `{...User, "privacy_settings": { ... } }`（不含 password_hash）。
`privacy_settings` 始终返回完整的 5 个键，即使全部为默认值。

### GET /users/search?q=
```json
// response 200
[ { "id":"", "username":"", "nickname":"", "avatar":"" } ]
```
支持 username / phone 模糊搜索（phone 仅匹配精确或后缀，避免泄露）。

---

## 3. Friend

### POST /friends/requests
```json
// request
{ "target_username_or_phone":"" }
// response 201 { ...FriendRequest } 或 200 已存在/已是好友
```

### GET /friends/requests?type=incoming|outgoing|all
response 200 → `[...FriendRequest]`（含对方 User 摘要）。

### POST /friends/requests/{id}/accept
response 200 → `{ "friendship":{...}, "conversation":{...} }`
（接受时建立双向 Friendship + 预创建规范化 Conversation）。

### POST /friends/requests/{id}/reject
response 200 → `{ "ok":true }`（request status → rejected）。

### GET /friends
response 200 → `[ { ...User, friendship_created_at } ]`。

### DELETE /friends/{friend_id}
response 200 → `{ "ok":true }`
删除：移除双向 Friendship；**保留历史消息**（V1 推荐），仅解除关系，禁止后续发消息。
（发消息前置校验 Friendship 是否存在，删除后 403。）

---

## 4. Conversation

### GET /conversations
response 200 → `[ { ...Conversation, peer:{...User}, last_message:{...}|null, unread_count } ]`
按 updated_at 倒序。

### GET /conversations/{id}
response 200 → `{ ...Conversation, peer:{...User} }`。
**越权防护**：非会话双方返回 403。

### GET /conversations/{id}/messages?cursor=&limit=
response 200 → `{ "items":[...Message], "next_cursor":"" }`
分页，按 created_at 升序。

### POST /conversations/{id}/messages
```json
// request
{ "content":"", "client_message_id":"" }
// response 201 { ...Message }  （服务端生成 id/created_at）
```
前置：双方为好友 + 是会话一方，否则 403。
去重：相同 (conversation_id, client_message_id) 返回已存消息（幂等）。

---

## 5. Device（设备管理，V1 特色）

### GET /devices
response 200 → `[ {...Device, is_current} ]`（手机端展示登录设备）。

### DELETE /devices/{id}
response 200 → `{ "ok":true }`
移除设备：吊销其 RefreshToken + 置 Device.revoked_at + 推送 `device.revoked` WS 事件，被移除端立即失去权限。

---

## 6. QR Desktop Login（V1 核心）

> **P1-2 冻结决策（方案 B：短轮询）**：
> - 轮询间隔 2–3 秒；QR Session 有效期 90 秒；**不使用未鉴权 WebSocket**。
> - QR 为**一次性 Session**；状态进入 AUTHORIZED 后立即停止轮询。
> - EXPIRED / CANCELLED / REJECTED 均停止轮询。
> - 网络异常：有限重试 + UI 提示，不无限轮询。
> - **安全边界分离（关键）**：`status` 轮询接口**只返回状态枚举，绝不返回用户数据或长期 Token**；授权成功后通过独立的一次性 `exchange` 接口用 `auth_code` 换取正式 Desktop Session；**获得正式 Token 后才建立已鉴权 WebSocket**。
> - 流程：`QR Session → 授权状态(仅状态) → Token Exchange(一次性 auth_code) → 正式 Desktop Session → 已鉴权 WS`。

### POST /auth/desktop/qr/create
```json
// request（桌面端无需 token，但需注册一个 pending desktop device）
{ "device_name":"Windows PC", "device_identifier":"" }
// response 200
{ "session_id":"", "nonce":"", "qr_payload":"chatapp://login?session=xxx&nonce=yyy", "expires_in":90, "status":"WAITING" }
```
桌面端拿到后展示二维码（qr_payload 编码进二维码），并开始每 2~3 秒轮询 status。

### GET /auth/desktop/qr/{session_id}/status
```json
// response 200 —— 仅返回状态，绝不携带 token / 用户数据
{ "status":"WAITING" }
// 手机扫码后
{ "status":"SCANNED" }
// 手机确认授权后
{ "status":"AUTHORIZED", "auth_code":"<一次性短时效授权码>" }
// 异常终态
{ "status":"EXPIRED" } | { "status":"CANCELLED" } | { "status":"REJECTED" }
```
- 轮询间隔 2~3s；`expires_in` 可在 WAITING/SCANNED 时返回剩余秒数（可选，非必须）。
- **AUTHORIZED 时仅附带一次性 `auth_code`**（短时效、单次使用），用于下一步 exchange；不返回 access/refresh token、不返回 user。
- 桌面端见到 AUTHORIZED / EXPIRED / CANCELLED / REJECTED 任一终态立即停止轮询。

### POST /auth/desktop/qr/exchange
```json
// request（桌面端，携带一次性 auth_code，无需 Bearer）
{ "session_id":"", "auth_code":"" }
// response 200 —— 换取正式 Desktop Session
{ "access_token":"", "refresh_token":"", "user":{...User}, "device":{...Device} }
// 失败：auth_code 无效/已用/过期 → 401 { "error":{ "code":"QR_EXCHANGE_INVALID" } }
```
- `auth_code` 一次性：兑换成功后立即失效（防重放）；与 session_id 绑定校验。
- 桌面端拿到 token 后：本地安全存储 RefreshToken → 用 access_token 建立**已鉴权 WebSocket** → 进入主界面。

### POST /auth/desktop/qr/scan
```json
// request（手机端已登录，带 Bearer）
{ "session_id":"", "nonce":"" }
// response 200
{ "status":"SCANNED", "device_name":"Windows PC", "scanned_at":"" }
```
服务端校验：session 存在 / 未过期 / 未使用 / 手机已登录。状态 WAITING→SCANNED（轮询端下次 poll 看到 SCANNED）。

### POST /auth/desktop/qr/confirm
```json
// request（手机端确认）
{ "session_id":"", "nonce":"", "action":"confirm|cancel" }
// response 200
// confirm → { "status":"CONFIRMED" }（服务端生成一次性 auth_code 并置状态 AUTHORIZED；下次 poll 返回 AUTHORIZED + auth_code）
// cancel  → { "status":"CANCELLED" }
```
confirm：绑定 user + desktop device，生成**一次性 auth_code**（短时效），状态置 CONFIRMED→AUTHORIZED，session 立即失效（REJECTED 防重放）。
cancel：状态置 CANCELLED，桌面端轮询看到后提示"已取消"并刷新二维码。

---

## 7. 错误响应统一格式
```json
{ "error": { "code":"FRIEND_NOT_FOUND", "message":"...", "status":404 } }
```
常用 code：UNAUTHENTICATED / FORBIDDEN / FRIEND_REQUIRED / CONVERSATION_FORBIDDEN / DUPLICATE_REQUEST / QR_EXPIRED / QR_USED / VALIDATION_ERROR。

## 8. 安全红线（实现必须遵守）
- 密码 bcrypt，绝不明文、绝不返回 password_hash。
- Access Token 短时效（如 15min），Refresh Token 可吊销 + 轮换。
- WebSocket 连接必须携 Bearer 或短期 ws ticket 鉴权。
- 二维码只含 session_id + nonce，绝不携 Token/密码。
- 所有写操作服务端校验身份与关系（Server First）。

---

## 9. V1.1 API 修订记录

| 修订项 | 类型 | 说明 |
|---|---|---|
| PATCH /users/me | 修订 | 支持 privacy_settings 字段（merge patch），包含 5 个键：read_receipt_enabled / online_status_visibility / typing_indicator_enabled / new_device_login_alert / message_retention。完整定义 validation 和默认值。 |
| GET /users/me | 修订 | 响应始终返回完整的 privacy_settings 对象（5 个键）。 |
| new_device_login_alert | 规范 | 唯一设置源，仅存在于 privacy_settings.new_device_login_alert。Devices 页面显示真实开关，Privacy 页面仅显示跳转链接，不得出现第二个独立字段。 |

**V1.1 API 原则**：privacy_settings 为 User 模型的 JSON 子字段，通过 PATCH /users/me 合并更新。不新增独立的 /privacy 端点，不新增独立的设置字段。所有隐私偏好集中在 User.privacy_settings 下，便于统一管理和同步。
