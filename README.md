# Quiet Messenger

> 极简私人通讯 — 安静、可靠、只属于你。

Quiet Messenger 是一款跨平台一对一即时通讯工具，专注于人与人之间最纯粹的连接。没有信息流，没有群聊，没有广告，没有 AI 助手——只有你和你的好友，以及一条安静可靠的消息通道。

---

## 核心特性

### 已实现（V1.1）

| 能力 | 说明 |
|------|------|
| **账号体系** | 手机号注册 / 登录 / JWT 鉴权 / Refresh Token / 安全存储 |
| **好友关系** | 用户搜索 / 好友请求 / 接受 / 拒绝 / 删除 / 实时请求通知 |
| **一对一聊天** | 文字消息 / 历史记录 / 游标分页 / 发送状态 / 失败重试 |
| **实时通信** | WebSocket 长连接 / 实时消息推送 / 自动重连 / 指数退避 / 心跳 |
| **在线状态** | 好友在线 / 离线实时同步 / 多设备连接计数 / 初始状态同步 |
| **离线消息** | 断连期间消息持久化 / 重连后自动恢复 / 幂等去重 / 顺序保证 |
| **多端登录** | Android + Desktop 同时在线 / 消息实时同步 / 登出隔离 / 设备管理 |
| **隐私设置** | 在线状态可见性 / 头像可见性 / 资料可见性 / 五项隐私开关 |
| **安全** | 端到端鉴权 / 会话成员校验 / IDOR 防护 / SQL 注入防护 / 敏感字段保护 |

### 路线图

- **V1.2** — 消息撤回 / 删除 / 搜索，拉黑与好友备注，会话免打扰 / 置顶，已读回执，Desktop UX 补齐
- **V1.3** — 图片 / 文件 / 语音消息，推送通知（FCM / APNs），后台消息提醒
- **V2.0** — 群聊，音视频通话，消息转发 / 引用 / 回复，贴纸系统，水平扩展

---

## 技术栈

### 后端

- **框架**：FastAPI（Python 3.11+）
- **ORM**：SQLAlchemy 2.0 + Alembic 迁移
- **数据库**：SQLite（开发）/ PostgreSQL（生产）
- **实时通信**：原生 WebSocket（无第三方消息中间件）
- **鉴权**：JWT（Access Token + Refresh Token，Rotation 策略）
- **部署**：Docker + Nginx 反向代理 + WSS 终止

### Android 客户端

- **框架**：Flutter 3.44 / Dart 3.12
- **状态管理**：Provider / ChangeNotifier
- **网络**：Dio + 拦截器（自动 Refresh / 401 处理）
- **实时**：自研 WebSocket RealtimeClient（多播事件订阅 / 重连退避 / 心跳）
- **安全存储**：flutter_secure_storage
- **构建**：Android SDK 36 / AGP 9.0 / Gradle 9.1 / JDK 17

### Desktop 客户端

- **框架**：PySide6（Qt for Python）
- **状态管理**：自研 Controller + 订阅者模式
- **网络**：requests + 自定义 API Client
- **实时**：自研 WebSocket RealtimeClient（与 Android 协议对齐）
- **凭据存储**：WinVault Keyring（Windows 凭据管理器）

---

## 架构概览

```
┌─────────────┐     WSS      ┌──────────────────┐     SQL      ┌────────────┐
│   Android   │ ◄──────────► │                  │ ◄──────────► │ PostgreSQL │
│  (Flutter)  │              │   FastAPI 后端    │              │  (生产)    │
└─────────────┘              │   - REST API      │              └────────────┘
                              │   - WebSocket     │
┌─────────────┐     WSS      │   - Auth/JWT      │
│   Desktop   │ ◄──────────► │   - Presence      │
│  (PySide6)  │              │   - Message Hub   │
└─────────────┘              └──────────────────┘
```

**设计原则：**
- REST = 持久化状态查询与操作
- WebSocket = 实时事件通知（消息 / 好友请求 / 在线状态）
- 重连恢复 = REST 状态最终一致性 + WebSocket 增量事件
- 单连接多订阅者 = 一个 WebSocket 连接驱动所有业务模块

---

## 项目结构

```
quiet-messenger/
├── backend/              # FastAPI 后端服务
│   ├── app/
│   │   ├── core/         # 配置 / 依赖 / 错误 / 安全
│   │   ├── db/           # 数据库基类
│   │   ├── models/       # SQLAlchemy 模型
│   │   ├── routers/      # REST 路由（auth / users / friends / conversations / devices / ws）
│   │   ├── schemas/      # Pydantic Schema
│   │   └── services/     # 业务逻辑 + ConnectionManager + Presence
│   ├── tests/            # pytest 测试套件（88 tests）
│   ├── Dockerfile
│   └── requirements.txt
├── flutter/              # Android 客户端（Flutter）
│   ├── lib/
│   │   ├── app/          # 应用入口 / 主题 / DI
│   │   ├── core/         # API Client / Realtime / Storage / EventEnvelope
│   │   └── features/     # auth / chat / friends / presence / devices / settings
│   ├── test/             # Flutter 测试（48 tests）
│   └── android/          # Android 原生配置
├── desktop/              # Desktop 客户端（PySide6）
│   ├── app/
│   │   ├── api/          # API Client / 配置
│   │   ├── core/         # 错误 / 声音服务
│   │   ├── features/     # auth / chat / friends / devices / settings
│   │   ├── realtime/     # WebSocket RealtimeClient
│   │   ├── router/       # 页面路由
│   │   ├── storage/      # Token 存储
│   │   └── theme/        # 主题 / 颜色 / 排版
│   └── tests/            # pytest 测试（36 tests）
├── shared/               # 双端共享契约（数据模型 / API / WS 协议 / 状态机 / 设计系统）
├── docs/                 # 架构 / 审计 / 安全 / 路线图文档
├── deploy/               # Nginx 配置 / 部署脚本
├── docker-compose.yml
└── README.md
```

---

## 快速开始

### 前置要求

- Python 3.11+
- Flutter 3.44+ / Dart 3.12+
- JDK 17
- Android SDK（Platform 36 / Build Tools 36.0.0）
- PostgreSQL（生产）或 SQLite（开发，零配置）

### 后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

API 文档：http://localhost:8000/docs

### Android

```bash
cd flutter
flutter pub get
flutter run                  # 连接设备或模拟器
flutter build apk --release  # 构建 Release APK
```

### Desktop

```bash
cd desktop
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m app.main
```

---

## 测试

| 端 | 命令 | 结果 |
|----|------|------|
| 后端 | `cd backend && pytest tests/ -q` | 88 passed |
| Desktop | `cd desktop && pytest tests/ -q` | 36 passed, 1 skipped |
| Android | `cd flutter && flutter analyze` | 0 errors |
| Android | `cd flutter && flutter test` | 48 passed |

---

## 产品哲学

> **安静。可靠。只属于你。**

Quiet Messenger 不追求功能数量，不做平台化，不做社交发现。

**我们做：**
- 人与人之间最纯粹的一对一连接
- 手机与电脑之间无缝的消息接力
- 不打扰、不推送垃圾、不追踪你的在线状态给陌生人

**我们不做：**
- 朋友圈 / 信息流 / 社区
- 群聊（V1.1）
- 小程序 / 支付 / 广告 / 游戏
- AI 聊天助手 / 智能推荐
- 陌生人社交 / 可能认识的人

每一个新功能都必须先回答：**它是否直接服务于"人与人的安静连接"？** 答案是否定的，就不做。

---

## 版本

| 版本 | 日期 | 说明 |
|------|------|------|
| **v1.1.0** | 2026-08-25 | 首个稳定 Release — 核心通讯能力完整（Auth / Friend / Conversation / Message / WebSocket / Presence / Offline Sync / Multi-device / Security） |

---

## 许可证

私有项目，未开源。保留所有权利。

---

*Quiet Messenger — 让消息回归安静。*
