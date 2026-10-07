/// 音效播放服务（应用级单例）。
///
/// 负责播放应用内通知音效，统一管理音量、开关、前后台、节流。
///
/// 业务事件 → Notifier/Event Layer → SoundService → AudioPlayer
/// UI 页面禁止直接调用 AudioPlayer。
///
/// 音效失败不影响业务逻辑（所有 play 方法均为 fire-and-forget，异常静默）。
library;

import 'package:audioplayers/audioplayers.dart';
import 'package:flutter/widgets.dart';

class SoundService with WidgetsBindingObserver {
  SoundService._() {
    WidgetsBinding.instance.addObserver(this);
  }

  static final SoundService instance = SoundService._();

  final AudioPlayer _player = AudioPlayer();

  // ---- 音效资源路径 ----
  static const String friendAdded = 'assets/sounds/friend_added.mp3';
  static const String newMessage = 'assets/sounds/new_message.mp3';
  // online.mp3 当前 BLOCKED：项目无 Presence Transition Event，资源也不存在。
  static const String online = 'assets/sounds/online.mp3';

  // ---- 配置 ----
  bool _enabled = true;
  double _volume = 0.5; // 适中音量，非 100%
  bool _foreground = true; // App 是否在前台

  // ---- 节流（friend_added）----
  // 短时间内多个新增好友请求只播放一次。
  static const Duration _friendThrottle = Duration(seconds: 3);
  DateTime? _lastFriendPlay;

  /// 是否启用音效播放。
  bool get enabled => _enabled;

  set enabled(bool value) {
    _enabled = value;
    if (!value) {
      _player.stop();
    }
  }

  /// 音效音量（0.0 ~ 1.0）。
  double get volume => _volume;

  set volume(double value) {
    _volume = value.clamp(0.0, 1.0);
  }

  /// App 是否在前台（由 WidgetsBinding 生命周期自动更新）。
  bool get foreground => _foreground;

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _foreground = state == AppLifecycleState.resumed;
    if (!_foreground) {
      _player.stop(); // 后台停止当前播放
    }
  }

  /// 内部播放：统一处理 enabled / foreground / volume / 异常。
  Future<void> _play(String assetPath) async {
    if (!_enabled || !_foreground) return;
    try {
      await _player.stop();
      await _player.setVolume(_volume);
      await _player.play(AssetSource(assetPath));
    } catch (_) {
      // 音效播放失败不影响应用主流程
    }
  }

  /// 播放加好友音效（收到别人的新好友请求时）。
  ///
  /// 自带节流：短时间内多次调用只播放一次。
  /// 调用方需先完成业务 ID 去重（FriendRequest.id），再调用本方法。
  Future<void> playFriendAdded() async {
    final now = DateTime.now();
    if (_lastFriendPlay != null &&
        now.difference(_lastFriendPlay!) < _friendThrottle) {
      return; // 节流窗口内，忽略
    }
    _lastFriendPlay = now;
    await _play(friendAdded);
  }

  /// 播放新消息音效。
  ///
  /// MessageNotifier 已通过 message.id 去重，此处直接播放。
  Future<void> playNewMessage() => _play(newMessage);

  /// 播放上线音效。
  ///
  /// 当前 BLOCKED：项目无可靠 Presence Transition Event（无后端 WebSocket
  /// user_online/user_offline 事件，无 User presence 字段，无 Flutter
  /// PresenceNotifier）。此方法为占位，调用为空操作。
  Future<void> playOnline() async {
    // ONLINE SOUND BLOCKED — 等待真实 Presence 事件链路完成后再接入。
  }

  /// 释放资源。
  Future<void> dispose() async {
    WidgetsBinding.instance.removeObserver(this);
    await _player.dispose();
  }
}
