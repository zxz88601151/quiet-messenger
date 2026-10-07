# 极简双端聊天软件 V1 — Phase 0 总结报告

> 生成时间：2026-08-23 20:08
> 状态：Phase 0 完成，可进入 Phase 1 Foundation

---

## 一、阶段目标
在编写任何业务代码之前，完成：
1. 技术栈确认
2. 项目目录结构
3. 数据库 Schema（8 表）
4. API Contract（REST 全量）
5. WebSocket Protocol
6. Auth 流程 / QR Login 协议
7. Friend / Conversation / Message / QR 状态机
8. 双端页面清单
9. 三端→双端共享数据模型定义
10. V1 风险清单
11. 开发顺序
12. Discovery Audit（架构可行性审计）

**Phase 0 禁止写业务代码 —— 已遵守。**

---

## 二、实际完成内容

### 2.1 交付物清单
| 文件 | 内容 | 状态 |
|------|------|------|
| `shared/DATA_MODEL.md` | 8 张核心表 Schema + 客户端映射约定 | ✅ |
| `shared/API_CONTRACT.md` | REST 全量（Auth/User/Friend/Conversation/Device/QR Login）+ 错误码 + 安全红线 | ✅ |
| `shared/WS_PROTOCOL.md` | WebSocket 帧协议、重连、离线补偿 | ✅ |
| `shared/STATE_MACHINES.md` | Friend/Friendship/Conversation/Message/QR/Device 六套状态机 | ✅ |
| `shared/UI_DESIGN_SYSTEM.md` | 颜色/字体/间距/组件 token | ✅ |
| `docs/PHASE0_AUDIT.md` | Discovery Audit + 双端边界红线 + P1-2 冻结决策 | ✅ |
| `README.md` | 项目说明 + Phase 1~8 路线 | ✅ |

### 2.2 关键架构决策（已冻结）
- **双端**：手机 Flutter + 电脑 PySide6，共用 1 个 FastAPI 后端。无 Web、无第三端（已加边界红线）。
- **数据模型 8 表**：User / Device / RefreshToken / QRLoginSession / FriendRequest / Friendship / Conversation / Message。
- **认证**：Access Token（短时效）+ Refresh Token（绑定设备、可吊销、轮换）。bcrypt 哈希密码。
- **好友**：FriendRequest(pending/accepted/rejected) + Friendship(双向写入去重)。
- **会话**：Conversation 按 min/max(user_a,user_b) 规范化，UNIQUE 去重，一对用户唯一会话。
- **消息**：client_message_id 幂等防重；状态 sending→sent→read。
- **二维码登录**：QR Session 一次性、90s、nonce 防重放；**状态轮询与 Token 发放分离**（见下）。

### 2.3 P1-2 二维码授权（用户拍板冻结）
- 方案 B 短轮询：间隔 2–3s，QR 有效期 90s，不使用未鉴权 WS。
- `GET /auth/desktop/qr/{session_id}/status` **只返回状态枚举**，AUTHORIZED 时仅附带一次性 `auth_code`，绝不返回长期 token/用户数据。
- `POST /auth/desktop/qr/exchange` 用一次性 auth_code 兑换正式 Desktop Session。
- 获得 token 后才建立已鉴权 WebSocket。
- 终态（AUTHORIZED/EXPIRED/CANCELLED/REJECTED）立即停止轮询；网络异常有限重试 + UI 提示。

### 2.4 UI 设计系统
- 白底 `#FFFFFF` + 主文字 `#111111` + 次文字 `#777777` + 边框 `#EAEAEA` + 品牌色蓝 `#2D7FF9` + 危险红 `#E5484D`。
- 禁止：渐变、玻璃拟态、复杂阴影、高饱和、过度圆角。
- 双端共享 design token，布局可平台化（Flutter Bottom Nav / PySide6 Sidebar）。

---

## 三、修改文件
- 新建：`shared/*`、`docs/PHASE0_AUDIT.md`、`README.md`、`docs/PHASE0_REPORT.md`（本报告）。
- 修订（2 轮）：清除"三端"措辞改为"双端"；P1-2 从"待拍板"改为"已冻结决策"（轮询 + 安全边界分离）。

---

## 四、API 变化
- 无历史 API 变化（Phase 0 首版冻结）。
- 最终 QR Login 接口集：`POST /auth/desktop/qr/create` · `GET /auth/desktop/qr/{session_id}/status` · `POST /auth/desktop/qr/scan` · `POST /auth/desktop/qr/confirm` · `POST /auth/desktop/qr/exchange`。

---

## 五、数据库变化
- 首版 8 表 Schema 冻结，无历史变更。

---

## 六、双端变化
- 无（Phase 0 未启动客户端）。

---

## 七、测试结果
- Phase 0 为只读设计阶段，无代码可测。
- 契约自审：状态机闭环、唯一约束、安全边界、双端一致性均已交叉核对，无 P0 矛盾。

---

## 八、发现的问题
| 问题 | 等级 | 处置 |
|------|------|------|
| 初版蓝图含 Web 端，与"双端"冲突 | P1 | 用户二次强调后，全量改为双端 + 加边界红线 |
| 桌面端扫码前无 Token 收授权 | P1 | 拍板方案 B 短轮询 + 状态/Token 分离 |
| 轮询接口直接返回 token 的安全隐患 | P1 | 用户建议拆分，已采纳冻结 |
| 手机号模糊搜索泄露风险 | P2 | 约定 phone 仅精确匹配 |
| 删好友后 Conversation 保留策略 | P2 | 保留会话行，仅删 Friendship，发消息前置校验 |
| 反向好友请求边界 | P2 | 实现时 service 层处理，记 Future |
| 已读批量标记语义 | P2 | 按会话 + sender != 自己 + created_at 批量置 read_at |

---

## 九、遗留问题
- 无 P0/P1 遗留。
- P2 项将在对应 Phase（Friend/Message）实现时处理。
- SQLite → PostgreSQL 切换：Phase 1 用 SQLite，Prod 切换留 env 开关，M6/M8 验证。

---

## 十、是否可以进入下一阶段
**✅ 可以。Phase 0 出口判据全部满足，无阻塞。**

---

# 下一步开发步骤建议（Phase 1 ~ Phase 8）

## Phase 1 — Foundation（建议优先做后端，双端并行搭壳）
**目标**：三端都能启动；后端具备 DB + Auth 基础设施。
- Backend：FastAPI 工程、SQLAlchemy 模型（8 表）、Alembic 初始化迁移、Pydantic schemas、core（config/db/security/deps）、CORS、基础日志/异常处理。
- 实现最小 Auth 骨架：`register` / `login` / `refresh` / `logout`（含 bcrypt、JWT、Device+RefreshToken 写入）。
- Mobile：Flutter 工程 + Riverpod + Dio + 路由骨架（Splash/Login/Register 空壳）。
- Desktop：PySide6 工程 + 主窗口骨架 + httpx/websockets 封装占位。
- 验收：三端均能启动；后端 `/docs` 可开；register→login 跑通拿 token。

## Phase 2 — Identity
- 完整 Auth：forgot/reset-password（Dev mock 验证码）、`GET/PATCH /users/me`、`/users/search`。
- 双端：登录/注册/找回密码/资料页 + token 持久化（Flutter Secure Storage / PySide6 keyring）。
- 验收：注册→登录→进主界面→刷新保持登录→退出 全链路。

## Phase 3 — Friend
- 后端：search / requests(发/列/接受/拒绝) / friends(列/删) + 双向 Friendship 写入 + 去重。
- 双端：搜索/好友列表/请求/接受拒绝/删除。
- 验收：A 搜 B→加→B 接受→双方好友→删→解除。

## Phase 4 — Conversation
- 后端：规范化 upsert Conversation + 列表 + 历史消息分页。
- 双端：聊天列表 + 聊天页 + 历史加载。
- 验收：好友→开聊→加载历史。

## Phase 5 — Real-time Chat
- 后端：WS 鉴权 + message.send/create/read + 广播 + conversation.updated。
- 双端：WS 连接 + 实时收发 + 已读/未读 + 断线重连 + 离线增量拉取。
- 验收：**Flutter A 发 → Web/PySide6 B 实时收**（注：本项为双端，即 Flutter↔PySide6 互通）+ 多端同步。

## Phase 6 — QR Desktop Login（核心特色）
- 后端：QRLoginSession 状态机 + create/scan/confirm/status/exchange 五接口 + Device 管理(列/删)。
- Desktop：QR 登录页（轮询 2–3s）+ 自动 refresh 登录 + 本地安全存 RefreshToken。
- Mobile：扫码 → 确认弹窗 → confirm。
- 验收：手机注册登录→电脑开→扫码→确认→电脑自动进→发消息手机实时收→关电脑重开自动登录→同步离线。

## Phase 7 — Client Polish
- 双端 UI 对齐 design token；错误提示/网络恢复/加载/空态/错误态自查。

## Phase 8 — Security & QA
- 按审计清单全链路测：QR 过期/重放/取消/双电脑、Auth 轮换/吊销、Friend 越权/重复、Message 重复/离线/多端。
- API/DB/Auth/Friendship/Conversation/Message/WS/双端 UI 逐项 Audit。

---

## 建议的执行顺序（务实）
1. **先后端后双端**：Backend 是单一事实源，先把它跑通，双端才有真后端联调。
2. **双端脚手架可在后端 Auth 骨架就绪后并行**，但不急着写业务 UI，先对齐 API client 封装。
3. **QR Login 放 Phase 6 而非更早**：它依赖 Identity(Device) + 完整 Auth，早做会返工。
4. **每个 Phase 严格按工作纪律输出阶段报告**（目标/完成/文件/API/DB/双端/测试/问题/遗留/可否进下一阶段）。
