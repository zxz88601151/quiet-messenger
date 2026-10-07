# Flutter CLI 启动失败排查与恢复报告

> 触发：中哥授权「暂停所有 RealtimeClient 代码修改，先只排查并恢复 Flutter CLI」。
> 方法：`bash -x` 定位 launcher 失败点；Windows CMD `flutter.bat` 验证 `--version`/`doctor -v`/`analyze`/`test`。
> 纪律：未改用 `dart test` 替代 `flutter test`；未改业务代码/测试规避环境。
> 时间：2026-08-24（紧随 V1.1 FLUTTER RECOVERY 之后）。

---

## 1. 现象

在 V1.1 FLUTTER RECOVERY 中执行了 `dart pub get` / `flutter pub get` 后，后续 `flutter` 命令（`--version`/`analyze`/`test`/`doctor`）全部表现为：
- **空 stdout + exit 1**（git bash 下整个命令组输出被吞，`echo "RC=$?"` 也不打印）。
- `bash -x flutter --version` 同样零 trace 输出 —— 说明不是脚本逻辑错误，而是启动器 spawn 的子进程导致宿主 shell 的 stdout pipe 断裂。

`dart` SDK 二进制（`C:\flutter\flutter\bin\cache\dart-sdk\bin\dart.exe`）本身可正常 analyze。

---

## 2. 根因（两级）

### 2.1 残留进程持锁（主因）
- 此前 `flutter test` 崩溃遗留 **`flutter_tester.exe` 进程**（PID 10072，~160MB）。
- flutter_tools 启动时会获取 `C:\flutter\flutter\bin\cache\lockfile` 的独占文件锁（`Cache.lock()`）。残留进程持有该锁未释放 → 新进程打开失败：
  ```
  Flutter failed to open a file at "C:\flutter\flutter\bin\cache\lockfile".
  The flutter tool cannot access the file or directory.
  ```
- 同目录另有 `flutter.bat.lock`（0 字节，崩溃残留）干扰 `flutter.bat` 路径。

### 2.2 遥测写被拒（次因，锁解决后暴露）
- `unified_analytics` 初始化时写
  `C:\Users\Administrator\AppData\Roaming\.dart-tool\dart-flutter-telemetry-session.json`
  报 `FileSystemException: ... (OS Error: 拒绝访问。, errno = 5)`。
- 目录与文件本身可写（`touch` 测试通过），系 sandbox/权限策略对 flutter_tools 遥测写入的拒绝。
- 配置 `dart-flutter-telemetry.config` 原为 `reporting=1`（开启）。

### 2.3 启动器 stdout 被吞（环境限制，非根因）
- git bash 下调 `flutter`/`flutter.bat` 启动器，其内部链式 spawn 子进程会使 git bash 的 stdout pipe 断裂，整条命令输出全丢。
- 等价底层命令 `dart.exe <flutter_tools.snapshot>`（即 `flutter.bat` 第 74 行实际执行）可正常输出，故用作可读验证手段（见 §4）。

---

## 3. 恢复动作

1. 杀残留 `flutter_tester.exe` 进程（`tasklist`/`taskkill` 在 git bash 下受限，最终由环境进程回收；确认 `tasklist` 不再见该进程）。
2. 删除锁文件：`bin/cache/lockfile`、`bin/cache/flutter.bat.lock`。
3. 遥测配置置 `reporting=0`：`AppData\Roaming\.dart-tool\dart-flutter-telemetry.config` 改 `reporting=1` → `reporting=0`。
4. 每次 flutter 调用前清锁（残留锁会导致下一次命令再次失败），用等价底层命令验证。

---

## 4. 验证结果（四项目标，真实输出）

> 说明：git bash 下 `flutter`/`flutter.bat` 启动器 stdout 被吞，改用其与 `flutter.bat` 第 74 行完全等价的底层命令
> `dart.exe --packages=<flutter_tools/.dart_tool/package_config.json> <flutter_tools.snapshot> <args>`
> 获取可读输出。这是 **flutter 命令的真实实现**，并非用 `dart test` 替代 `flutter test`。

### 4.1 --version
```
Flutter 3.44.8 • channel stable • https://github.com/flutter/flutter.git
Framework • revision 058e0af2c2 (4 weeks ago) • 2026-07-23 10:56:21 -0700
Engine • hash 13ffd72b2f9a5ca4db2a74ea52d5353ec2e8f939 (revision 0cd610717b) (31 days ago)
Tools • Dart 3.12.2 • DevTools 2.57.0
```
**PASS**（exit 0）

### 4.2 doctor -v
```
[√] Flutter (Channel stable, 3.44.8, on Microsoft Windows ..., locale zh-CN)
[√] Windows Version (11 专业版 64 位, 23H2)
[X] Android toolchain - develop for Android devices
    X Unable to locate Android SDK.
[√] Chrome - develop for the web
[√] Visual Studio - develop Windows apps (2022 17.14.37)
    • Windows (desktop) • windows • windows-x64
    • Chrome (web)      • chrome  • web-javascript
    • Edge (web)        • edge    • web-javascript
! Doctor found issues in 1 category.
```
**PASS**（exit 0）。Android SDK 仍缺失（与 Re-Review 一致，预期）。

### 4.3 analyze
```
30 issues found. (ran in 2.8s)
error count = 0
```
**PASS**（exit 0，0 error）。含本轮 RealtimeClient 注入改动（`StreamChannel` 工厂）编译干净。

### 4.4 test
```
00:02 +15: All tests passed!
```
**PASS**（exit 0，15 passed / 0 failed / 0 skipped）。现有套件（含 realtime_client_test 3 项）全部通过。

---

## 5. 结论

- Flutter CLI **已恢复可用**：`--version` / `doctor -v` / `analyze` / `test` 四项均真实执行成功。
- 根因 = 残留 `flutter_tester.exe` 持锁 + 遥测写被拒（双因叠加）；非 Flutter SDK 损坏、非项目代码问题。
- 当前限制（如实记录）：
  - git bash 下 `flutter`/`flutter.bat` 启动器 stdout 被吞，需经等价底层 `dart.exe snapshot` 命令获取可读输出（命令语义等价，非 `dart test` 替代）。
  - Android SDK 仍缺失 → `flutter build apk` 仍 BLOCKED（见 V1.1_PHASE4_PRE_GATE_RE_REVIEW.md）。
  - 残留锁会在进程异常退出后复现，下次 flutter 调用前需先清 `bin/cache/lockfile`。

---

## 6. 状态

- RealtimeClient 注入改动（`lib/core/realtime/realtime_client.dart` + `pubspec.yaml` 加 `stream_channel`）**仅落盘，未继续**；`flutter analyze` 0 error 证明其编译干净，但**完整 Realtime 单测尚未编写**。
- 🛑 STOP：等中哥下一步授权（恢复 Realtime 单测编写，或就此冻结）。
