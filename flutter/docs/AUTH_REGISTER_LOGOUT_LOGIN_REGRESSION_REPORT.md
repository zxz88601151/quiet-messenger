# AUTH REGRESSION REPORT: Register → Login → Logout → Login Again

> 调查类型：READ-ONLY / TEST + ROOT-CAUSE INVESTIGATION
> 调查时间：2026-08-25
> 测试环境：Staging API (https://api.example.com/api/v1)
> 客户端：Flutter Android (Release APK)

---

## 1. Executive Summary

本次调查确认了**两个独立的严重问题**：

| # | 问题 | 严重度 | 根因 | 状态 |
|---|------|--------|------|------|
| 1 | Logout 后使用相同设备重新登录返回 **500 Internal Server Error** | 🔴 CRITICAL | 后端 Device 唯一约束冲突（revoked 设备未重新激活） | 本地已修复，**未部署到 Staging** |
| 2 | Login 失败时 Android UI **无任何错误提示** | 🔴 CRITICAL | ApiClient 用 DioException 包装 ApiException，但 AuthNotifier 只 catch ApiException，异常未被捕获 | **未修复** |

---

## 2. Test Environment

- API Base: `https://api.example.com/api/v1`
- 测试账号：全新生成（`regtest_4ad54483` / `19887591795`）
- Device ID: `regtest-device-b4740514`
- 后端：Nginx 1.24.0 (Ubuntu) + FastAPI

---

## 3. Full Lifecycle Test Results

### Step 1: Register

| 项目 | 值 |
|------|-----|
| HTTP Status | **201 Created** |
| User ID | `8d864374-c244-4189-8f57-e7de45b6b5b5` |
| Username | `regtest_4ad54483` |
| Phone | `19887591795` |
| Device ID | `2f810e4e-4208-4d57-b943-6481a31465e9` |
| Device revoked_at | `null` |

✅ Register 成功。

### Step 2: GET /users/me (确认账号存在)

| 项目 | 值 |
|------|-----|
| HTTP Status | **200 OK** |
| User ID | 匹配 |

✅ 账号存在。

### Step 3: Login #1 (相同 device_identifier)

| 项目 | 值 |
|------|-----|
| HTTP Status | **200 OK** |
| Device ID | `2f810e4e-4208-4d57-b943-6481a31465e9`（复用同一设备） |
| Device revoked_at | `null` |

✅ Login #1 成功，设备被正确复用。

### Step 4: Logout

| 项目 | 值 |
|------|-----|
| HTTP Status | **200 OK** |
| Response | `{"ok": true}` |

✅ Logout 成功（后端 revoke refresh token + device revoked_at）。

### Step 5: Login #2 (Logout 后，相同 credentials + 相同 device_identifier)

| 项目 | 值 |
|------|-----|
| HTTP Status | **500 Internal Server Error** ❌ |
| Content-Type | `text/plain; charset=utf-8` |
| Response Body | `Internal Server Error` |

❌ **Login #2 失败：500 Internal Server Error**

### Step 6: Login #2b (相同 credentials + **不同** device_identifier)

| 项目 | 值 |
|------|-----|
| HTTP Status | **200 OK** ✅ |
| New Device ID | `8218c6dd-18b3-4c89-be13-9096a55c10b7` |

✅ 使用不同 device_identifier 登录成功。

> **关键证据**：相同设备 → 500；不同设备 → 200。证明问题出在 Device 唯一约束冲突。

### Step 7: Re-register (确认账号仍然存在)

| 项目 | 值 |
|------|-----|
| HTTP Status | **409 Conflict** |
| Error Code | `DUPLICATE_USER` |
| Message | `用户名或手机号已存在` |

✅ 账号未被删除，仍然存在。

### Step 8: Wrong Password (验证 401 行为)

| 项目 | 值 |
|------|-----|
| HTTP Status | **401 Unauthorized** |
| Error Code | `INVALID_CREDENTIALS` |
| Message | `账号或密码错误` |

✅ 后端 401 行为正确。

### Step 9: Old Refresh Token after Logout (安全检查)

| 项目 | 值 |
|------|-----|
| HTTP Status | **401 Unauthorized** |
| Error Code | `UNAUTHENTICATED` |
| Message | `Refresh Token 无效、已过期或被吊销` |

✅ Refresh Token 在 Logout 后被正确 revoke。

---

## 4. Root Cause #1: Backend 500 (Login After Logout)

### 4.1 问题描述

一个刚注册、刚登录成功的账号，在执行 Logout 后，使用**相同的 device_identifier** 再次 Login，后端返回 **500 Internal Server Error**。

### 4.2 根因分析

**后端代码位置**：`backend/app/services/auth_service.py` → `_bind_or_get_device()`

**Device 模型唯一约束**（`backend/app/models/device.py`）：
```python
UniqueConstraint("user_id", "device_identifier", name="uq_devices_user_identifier")
```

**Logout 行为**（`auth_service.py` `logout()`）：
```python
dev.revoked_at = _now()  # 标记设备为 revoked
```

**重新登录时 `_bind_or_get_device` 的旧逻辑**（修复前）：
```python
# 只查找 revoked_at IS NULL 的设备
dev = db.execute(
    select(Device).where(
        Device.user_id == user.id,
        Device.device_identifier == device_in.device_identifier,
        Device.revoked_at.is_(None),  # ← 只找非 revoked 设备
    )
).scalar_one_or_none()

if dev is None:
    # 找不到 → 创建设备
    dev = Device(...)  # ← 但同一 device_identifier 已有 revoked 行
    db.add(dev)
    db.commit()  # ← 违反唯一约束 → IntegrityError → 500
```

**因果链**：
```
Logout → device.revoked_at = now
    ↓
Re-login (same device_identifier)
    ↓
_bind_or_get_device 查询 revoked_at IS NULL → 找不到
    ↓
尝试创建新 Device (same user_id + device_identifier)
    ↓
违反 UniqueConstraint(user_id, device_identifier)
    ↓
IntegrityError → 未捕获 → 500 Internal Server Error
```

### 4.3 关键证据

| 测试 | device_identifier | 结果 |
|------|-------------------|------|
| Login #2 | 相同 (`regtest-device-b4740514`) | **500** |
| Login #2b | 不同 (`regtest-device-b4740514-NEW`) | **200** |

### 4.4 修复状态

✅ **本地已修复**：`_bind_or_get_device` 新增 revoked 设备查询，找到后重新激活（清除 revoked_at，更新设备信息），而非新建。

❌ **未部署到 Staging**：Staging 服务器仍运行旧代码，500 问题仍然存在。

---

## 5. Root Cause #2: Android UI 无错误提示

### 5.1 问题描述

Login 失败时（无论是 401 密码错误、500 服务器错误、还是网络错误），Android UI **不显示任何错误提示**。用户看到的是：点击登录 → loading spinner → spinner 停止 → 页面无变化 → "无任何反应"。

### 5.2 根因分析

**异常包装链**：

1. **ApiClient**（`lib/core/api/api_client.dart` 第92-107行 `_normalize()`）：
   ```dart
   DioException _normalize(DioException err) {
     // 解析后端 error JSON → ApiException
     return err.copyWith(
       error: ApiException(code: code ?? 'UNKNOWN', message: message ?? ..., status: ...),
     );
   }
   ```
   ApiClient 将 ApiException **包装在 DioException 的 error 属性中**，抛出的是 `DioException`，不是 `ApiException`。

2. **AuthNotifier**（`lib/features/auth/auth_notifier.dart` 第47-58行 `login()`）：
   ```dart
   Future<void> login({...}) async {
     _beginLoading();
     try {
       _session = await _repo.login(...);  // ← 抛出 DioException，不是 ApiException
       _status = AuthState.authenticated;
       _error = null;
     } on ApiException catch (e) {  // ← 只 catch ApiException！
       _fail(e);                      // ← 永远不会执行
     } finally {
       _endLoading();
     }
   }
   ```

3. **结果**：`DioException` 不被 `on ApiException` 捕获，异常向上传播（可能被 Flutter framework 捕获为 unhandled exception），`_error` 永远为 `null`。

4. **LoginPage**（`lib/features/auth/pages/login_page.dart` 第67行）：
   ```dart
   if (auth.error != null)  // ← 永远为 null
     Text(auth.error!.message, ...)  // ← 永远不显示
   ```

### 5.3 影响范围

| 方法 | 是否受影响 |
|------|-----------|
| `AuthNotifier.login()` | ✅ 受影响（`on ApiException`） |
| `AuthNotifier.register()` | ✅ 受影响（`on ApiException`） |
| `AuthNotifier.logout()` | ⚠️ 部分（catch ApiException，但 logout 失败也会清除本地状态） |
| `AuthNotifier.handleUnauthorized()` | ✅ 受影响（`on ApiException`） |

**所有 AuthNotifier 的 API 错误都不会被正确捕获和显示。**

### 5.4 auth_error_mapper 本身正确

`lib/features/auth/auth_error_mapper.dart` 的 `mapAuthError()` 函数正确映射了错误码：
- `INVALID_CREDENTIALS` → "用户名或密码错误，请重试"
- `VALIDATION_ERROR` → "输入有误：..."
- `NETWORK_ERROR` → "网络异常，请检查连接后重试"
- `default` → "操作失败，请稍后重试"

但因为异常从未被捕获，这个 mapper 从未被调用。

### 5.5 修复状态

❌ **未修复**。需要在 AuthNotifier 中同时 catch `DioException` 并从中提取 `ApiException`，或者在 ApiClient 层直接抛出 `ApiException` 而非包装在 `DioException` 中。

---

## 6. Token Lifecycle

### 6.1 Refresh Token

| 测试 | 结果 |
|------|------|
| Logout 后使用旧 Refresh Token 调用 /auth/refresh | **401 UNAUTHENTICATED** ✅ |
| 错误信息 | "Refresh Token 无效、已过期或被吊销" |

✅ Refresh Token 在 Logout 后被正确 revoke。

### 6.2 Access Token

- Access Token 为 JWT 无状态设计，TTL = 30 分钟
- Logout 后 Access Token 在过期前仍然有效（JWT 无状态，后端不维护黑名单）
- 这是 **KNOWN JWT DESIGN**，不是 bug
- 如果产品要求 Logout 后立即失效，需要实现 Token Blacklist / 缩短 Access TTL / 改用有状态 Session

---

## 7. Account Status After Logout

| 检查项 | 结果 |
|--------|------|
| 账号是否被删除 | ❌ 未删除（re-register 返回 409 DUPLICATE_USER） |
| 账号是否被禁用 | ❌ 未禁用（使用不同 device_identifier 可正常登录） |
| User ID 是否一致 | ✅ 一致 |
| 密码是否被重置 | ❌ 未重置（相同密码可登录） |

✅ Logout 只做了 Session Cleanup + Device Revoke，未影响账号本身。

---

## 8. Android Auth State

| 状态 | Logout 后 | Login 失败后 |
|------|-----------|-------------|
| `isAuthenticated` | `false` ✅ | 保持之前状态（异常未捕获）⚠️ |
| `currentUser` | `null` ✅ | 保持之前值 ⚠️ |
| `loading` | `false` ✅ | `false`（finally 中结束）✅ |
| `error` | `null` ✅ | `null`（异常未捕获，_fail 未调用）❌ |

---

## 9. Token Storage

| 操作 | Access Token | Refresh Token |
|------|-------------|---------------|
| Login 成功 | ✅ 保存 | ✅ 保存 |
| Logout | ✅ 清除 (`_tokens.clear()`) | ✅ 清除 |
| Login 失败 | 保持空（异常前未设置） | 保持空 |

✅ Token Storage 逻辑正确。Logout 后本地 token 被正确清除。再次 Login 成功后新 token 可正常保存。

---

## 10. Multi-Account Test

本次调查使用单账号完成完整生命周期。根据代码分析：
- AuthNotifier 是单例（通过 Provider 共享），logout 后 `_session = null`，不会残留前一个账号数据
- 切换账号时新登录会覆盖 `_session`
- 但因为 Login 异常未被捕获（Root Cause #2），Login 失败时 `_session` 不会被清除（如果之前有 session）

---

## 11. Process Kill / Network Test

本次调查未执行 App Kill / Network Switch 测试（READ-ONLY API 调查）。根据代码分析：
- App Kill 后 TokenStorage 持久化，restoreSession() 会尝试 refresh
- Network 错误会被 ApiClient 包装为 DioException，同样不被 AuthNotifier 捕获（Root Cause #2）

---

## 12. Severity Assessment

| 问题 | 严重度 | 影响 |
|------|--------|------|
| #1 Backend 500 (Login after Logout) | 🔴 CRITICAL | 所有用户登出后无法在同一设备重新登录 |
| #2 Android UI no error | 🔴 CRITICAL | 所有登录/注册错误对用户不可见，表现为"无反应" |

两个问题组合导致用户体验：**注册→登录→登出→无法登录→无任何错误提示→用户困惑**。

---

## 13. Recommended Fix

### Fix #1: Backend (已本地修复，待部署)

部署已修复的 `auth_service.py` 到 Staging：
- `_bind_or_get_device` 新增 revoked 设备查询与重新激活逻辑
- 已通过本地测试（88 tests passed）

### Fix #2: Android AuthNotifier (待修复)

**方案 A（推荐）**：在 AuthNotifier 中同时 catch DioException：
```dart
} on ApiException catch (e) {
  _fail(e);
} on DioException catch (e) {
  final apiErr = e.error is ApiException ? e.error as ApiException : const ApiException(code: 'NETWORK_ERROR', message: '网络异常');
  _fail(apiErr);
}
```

**方案 B**：在 ApiClient 层直接抛出 ApiException（需要修改 ApiClient 设计，影响范围更大）。

---

## 14. Final Gate

| 检查项 | 结果 |
|--------|------|
| Register → Login → Logout → Login Again | ❌ **FAIL**（Login #2 返回 500） |
| Login 错误 UI 提示 | ❌ **FAIL**（无任何提示） |
| Account 存在性 | ✅ PASS |
| Refresh Token revoke | ✅ PASS |
| Token Storage 清除 | ✅ PASS |
| Wrong password 401 | ✅ PASS（后端正确，UI 不显示） |

### 最终判定

**AUTH REGRESSION = FAIL**

两个 CRITICAL 问题：
1. Backend 500（本地已修复，待部署）
2. Android UI 无错误提示（待修复）

---

## 15. 两个核心问题的明确结论

### Q1: 为什么一个刚注册、刚登录成功的账号 Logout 后无法再次 Login？

**A**: 后端 `_bind_or_get_device` 在重新登录时只查找 `revoked_at IS NULL` 的设备。Logout 将设备标记为 revoked，重新登录时找不到非 revoked 设备，尝试新建设备，但同一 `(user_id, device_identifier)` 已有 revoked 行，违反唯一约束 → IntegrityError → **500 Internal Server Error**。使用不同 device_identifier 可正常登录（200），证明根因是设备唯一约束冲突。本地已修复（revoked 设备重新激活），但未部署到 Staging。

### Q2: 为什么 Login 失败时 Android 没有给用户任何提示？

**A**: ApiClient 将后端错误包装为 `DioException(error: ApiException(...))` 抛出，但 AuthNotifier.login() 只 catch `on ApiException`。`DioException` 不是 `ApiException`，异常未被捕获，`_error` 永远为 null。LoginPage 检查 `if (auth.error != null)` 永远为 false，因此不显示任何错误文本。用户看到的只是 loading spinner 停止，页面无变化。此问题影响 login、register 等所有 AuthNotifier 方法。

---

**STOP — 等待授权修复。**
