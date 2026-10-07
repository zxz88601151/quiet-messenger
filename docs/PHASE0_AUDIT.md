# Phase 0 — Discovery Audit（架构可行性 & 完整性审计）

> 依据：用户提供的《极简双端聊天软件 V1》蓝图（手机 Flutter + Windows PySide6 + FastAPI 后端）。
> 立场：只读审计，不写业务代码。发现矛盾/遗漏/风险必须显式报告，不为"PASS"隐藏。
> 审计结论：蓝图**整体可行**，存在 6 项需冻结前决策的问题（P1×2 / P2×4），无 P0 阻塞。

---

## ✅ 已确认（蓝图清晰，无需质疑）
1. 双端 + 单后端架构合理，Server First 原则明确。
2. User / Device 分离是正确抽象，扫码登录安全模型（短生命周期 session + nonce + 服务端确认）设计到位。
3. Conversation 用 min/max 规范化去重，正确。
4. Message 引入 client_message_id 幂等防重，正确。
5. 8 张表边界清晰，无过度扩展。
6. UI Design Language 统一策略（token 一致、布局可异）合理。

---

## ⚠️ P1 — 必须决策（影响契约冻结）

### P1-1：桌面端"自动登录"与 QR 的耦合时序
蓝图 §31 桌面默认不输密码、只扫码；§17 又说登录后存 RefreshToken、以后启动走 refresh 免扫码。
**冲突点**：桌面端"是否已登录"的状态从哪来？首启无 Token → 必须扫码；有 Token → 直接 refresh。
**决策**：桌面端本地安全存储 RefreshToken（Windows Credential Store / keyring）。启动流程：
  - 有有效 RefreshToken → `/auth/refresh` → 进主界面（不显示 QR）。
  - 无 / 已吊销 / 过期 → 显示 QR 登录页。
**结论**：已在 API_CONTRACT 的 `qr/create` + `refresh` 体现，审计通过，但需在 M6 实测"吊销后桌面是否真的回到 QR 页"。

### P1-2：桌面扫码前收授权（✅ 已冻结决策）
**方案 B（短轮询）参数冻结：**

| 项目 | 值 |
|------|-----|
| 方案 | B：短轮询 |
| 轮询间隔 | 2–3 秒 |
| QR 有效期 | 90 秒 |
| 未鉴权 WS | 不使用 |
| QR | 一次性 Session |
| 授权成功 | 立即停止轮询 |
| EXPIRED / CANCELLED / REJECTED | 停止轮询 |
| 网络异常 | 有限重试 + UI 提示 |
| 正式 WS | 获得 Desktop Token 后再建立 |

**安全边界分离（用户补充冻结，采纳）：** `GET /auth/desktop/qr/{session_id}/status` **只返回状态枚举**（`WAITING`/`SCANNED`/`AUTHORIZED`/`EXPIRED`/`CANCELLED`/`REJECTED`），AUTHORIZED 时仅附带一次性 `auth_code`，**绝不返回长期 Access/Refresh Token 或用户数据**。授权成功后由独立接口 `POST /auth/desktop/qr/exchange` 用一次性 `auth_code` 兑换正式 Desktop Session，随后才建立已鉴权 WebSocket。

**理由：** 把"QR Session → 授权状态(仅状态) → Token Exchange(一次性 auth_code) → 正式 Desktop Session → 已鉴权 WS"的安全边界彻底分开，避免轮询响应携带长期凭证、降低中间人截获风险。

**结论：** 该决策可直接冻结，已写入 API_CONTRACT / WS_PROTOCOL / STATE_MACHINES。

---

## ⚠️ P2 — 需明确（不阻塞，但实现时易踩坑）

### P2-1：手机号搜索的隐私边界
蓝图 §36 `GET /users/search` 支持 username/phone 搜索。若 phone 可模糊搜，易泄露用户。**
**建议**：phone 仅支持**精确匹配**（输入完整手机号才返回），username 支持前缀/包含匹配。已在 API_CONTRACT 注明。

### P2-2：删除好友后 Conversation 是否保留
蓝图 §20/§21 未明说删除好友后 Conversation 行是否删。数据模型 §Friendship 说"保留历史消息"。
**建议**：保留 Conversation 行（消息才能查），仅删 Friendship；发消息前置 Friendship 校验 → 删除后 403。已写入 API_CONTRACT `DELETE /friends/{id}` 注释。

### P2-3：好友请求方向唯一约束的边界
A→B pending 时，B→A 再发如何处理？蓝图未说。
**建议**：B→A 时检测到反向 pending → 视为"互相添加"，可直接 accepted（或提示已收到请求）。实现时在 service 层处理，本期记 Future。

### P2-4：消息 read_at 的批量标记
蓝图 `message.read` 带 last_read_message_id，需明确是"标记该会话所有 ≤ 该消息的未读为已读"。
**建议**：服务端按 conversation_id + sender_id != 自己 + created_at <= 该消息 created_at 批量置 read_at。已写入 WS_PROTOCOL。

---

## 🔒 安全审计（红线确认）
| 项 | 状态 |
|----|------|
| 密码 bcrypt 哈希 | ✅ 要求明确 |
| Token 不落二维码 | ✅ session+nonce 设计正确 |
| QR 一次性/短时效/防重放 | ✅ nonce + EXPIRED/REJECTED 状态机 |
| WS 鉴权 | ⚠️ 见 P1-2（pending 连接需特殊设计，已选轮询降级） |
| 越权访问 Conversation | ✅ 403 前置校验 |
| 删除好友后禁发消息 | ✅ Friendship 校验 |
| RefreshToken 吊销/轮换 | ✅ 设备移除即时失效 |

---

## 📋 双端页面清单（冻结）

### Flutter（14 屏，蓝图 §25）
Splash / Login / Register / ForgotPassword / ChatList / Chat / Friends / FriendRequests / SearchUser / Profile / Settings / DeviceManagement / QRScanner / DesktopLoginConfirm

### PySide6（7 区，蓝图 §30）
QRLogin / MainWindow(Chats) / Chat / Friends / Profile / Settings / DeviceAccount
实际以 MainWindow + 左侧导航切换为主。

---

## 📊 风险清单（V1）
| 风险 | 等级 | 缓解 |
|------|------|------|
| 桌面端无 Token 收授权（P1-2） | 中 | 轮询降级 |
| 设备移除后桌面未即时失效 | 中 | WS device.revoked + 启动时 refresh 校验 |
| 网络重试消息重复 | 中 | client_message_id 唯一约束幂等 |
| WS 断线丢消息 | 低 | REST 增量拉取补偿 |
| 多端已读状态不一致 | 低 | message.read 广播 + 拉取时计算 |
| SQLite → PostgreSQL 切换方言问题 | 低 | SQLAlchemy 抽象，避免方言 SQL |
| 扫码中间人（同 WiFi） | 低 | HTTPS + nonce，V1 不做双向证书 |

---

## ⚠️ Phase 0 诚实声明（不隐藏缺口）
- 技术架构侧（API Contract / 数据模型 / WS / 状态机 / 安全 / 环境策略）**已全部冻结**。
- UI/UX 原型侧：**Design System（颜色/字体/间距/组件 token）已冻结**，双端页面线框/原型**由用户另行制作，不在本侧产出范围**；待用户完成后由本 Agent 介入检查。
- **处置**：Phase 0 对本 Agent 而言已收尾，无阻塞。UI 交付与检查节点顺延至用户完成原型后。

---

## ✅ Phase 0 出口判定
- [x] 技术栈确认
- [x] 数据模型（8 表）
- [x] API Contract（REST 全量）
- [x] WebSocket Protocol
- [x] QR Login Protocol + 状态机
- [x] Security Model
- [x] 双端页面清单
- [x] UI Design System
- [x] 项目目录（shared/ 单一事实源）
- [x] 风险清单
- [x] 开发顺序（Phase 1~8）
- [x] Discovery Audit（本文件）

**结论：Phase 0 通过，可进入 Phase 1 Foundation。**
**已拍板**：P1-2 方案 B 短轮询（状态接口只返回状态枚举 + 一次性 auth_code，token 走独立 exchange）；品牌色取蓝 `#2D7FF9`。
**剩余唯一待办**：无。可进入 Phase 1。

---

## 🚫 双端边界红线（V1 冻结，不可逾越）

**本项目只有两个客户端，绝不引入第三端：**

| 角色 | 技术 | 平台 |
|------|------|------|
| 手机端 | Flutter (Dart) | iOS / Android |
| 电脑端 | Python + PySide6 | Windows |

- **禁止**开发 Web 客户端 / 浏览器版 / H5 版（蓝图 §4 明确排除 "Web 客户端"）。
- **禁止**把电脑端做成 Web 套壳（必须用原生 PySide6，不是 Electron/WebView）。
- **禁止**为"未来多端"预留 Web 接口分支或抽象出第三套 UI。
- 契约层 `shared/` 的"双端唯一事实源"即为此意：手机 + 电脑共用同一后端、同一数据模型、同一 API、同一 WS 协议、同一 Design Token，不存在第三套。
- 任何新需求先问："它服务于手机或电脑双端吗？" 不属于 → V1 暂不实现。
