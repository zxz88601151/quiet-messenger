/// Privacy Settings — V1.1 MUST HAVE #3.
///
/// 5 keys from API_CONTRACT §2 PATCH /users/me (merge patch):
/// - read_receipt_enabled (bool, default true)
/// - online_status_visibility (all|none, default all)
/// - typing_indicator_enabled (bool, default true)
/// - new_device_login_alert (bool, default true) — unique source, also shown in Devices
/// - message_retention (forever|30_days|1_year, default forever)
///
/// Every change is persisted via PATCH /users/me and reflected in
/// AuthNotifier.currentUser.privacySettings. No local-only state.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../app/theme/colors.dart';
import '../../../app/theme/typography.dart';
import '../../auth/auth_notifier.dart';
import '../../auth/models/user.dart';
import '../repositories/user_repository.dart';

class PrivacySettingsPage extends StatefulWidget {
  const PrivacySettingsPage({super.key});

  @override
  State<PrivacySettingsPage> createState() => _PrivacySettingsPageState();
}

class _PrivacySettingsPageState extends State<PrivacySettingsPage> {
  bool _saving = false;

  Map<String, dynamic> get _defaults => const {
        'read_receipt_enabled': true,
        'online_status_visibility': 'all',
        'typing_indicator_enabled': true,
        'new_device_login_alert': true,
        'message_retention': 'forever',
      };

  dynamic _value(User user, String key) =>
      user.privacySettings[key] ?? _defaults[key];

  Future<void> _patch(User user, String key, dynamic value) async {
    setState(() => _saving = true);
    try {
      final repo = context.read<UserRepository>();
      final updated = await repo.patchMe({
        'privacy_settings': {key: value},
      });
      if (mounted) {
        context.read<AuthNotifier>().updateCurrentUser(updated);
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('保存失败: ${e.toString().split('\n').first}'),
            backgroundColor: AppColors.error,
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthNotifier>();
    final user = auth.currentUser;

    return Scaffold(
      appBar: AppBar(
        title: const Text('隐私设置'),
        actions: [
          if (_saving)
            const Padding(
              padding: EdgeInsets.only(right: 16),
              child: Center(
                child: SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
              ),
            ),
        ],
      ),
      body: user == null
          ? const Center(child: Text('请先登录'))
          : ListView(
              children: [
                _buildBoolTile(
                  user,
                  key: 'read_receipt_enabled',
                  title: '已读回执',
                  subtitle: '开启后，双方可看到消息已读状态',
                ),
                _buildBoolTile(
                  user,
                  key: 'typing_indicator_enabled',
                  title: '正在输入',
                  subtitle: '开启后，双方可看到正在输入提示',
                ),
                _buildBoolTile(
                  user,
                  key: 'new_device_login_alert',
                  title: '新设备登录提醒',
                  subtitle: '新设备登录时发送通知',
                ),
                _buildSelectTile(
                  user,
                  key: 'online_status_visibility',
                  title: '在线状态可见性',
                  options: const {'all': '所有人', 'none': '不可见'},
                ),
                _buildSelectTile(
                  user,
                  key: 'message_retention',
                  title: '消息保留',
                  options: const {
                    'forever': '永久保留',
                    '30_days': '30 天',
                    '1_year': '1 年',
                  },
                ),
                const SizedBox(height: 16),
                const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 16),
                  child: Text(
                    '所有设置实时保存到服务器，重新登录后保持一致。',
                    style: TextStyle(fontSize: 12, color: AppColors.text3),
                  ),
                ),
              ],
            ),
    );
  }

  Widget _buildBoolTile(
    User user, {
    required String key,
    required String title,
    required String subtitle,
  }) {
    final value = _value(user, key) == true;
    return SwitchListTile(
      title: Text(title, style: AppTypography.subtitle),
      subtitle: Text(subtitle, style: AppTypography.caption),
      value: value,
      onChanged: _saving ? null : (v) => _patch(user, key, v),
    );
  }

  Widget _buildSelectTile(
    User user, {
    required String key,
    required String title,
    required Map<String, String> options,
  }) {
    final current = _value(user, key) as String;
    return ListTile(
      title: Text(title, style: AppTypography.subtitle),
      subtitle: Text(options[current] ?? current, style: AppTypography.caption),
      trailing: DropdownButton<String>(
        value: options.containsKey(current) ? current : options.keys.first,
        items: options.entries
            .map((e) => DropdownMenuItem(value: e.key, child: Text(e.value)))
            .toList(),
        onChanged: _saving
            ? null
            : (v) {
                if (v != null) _patch(user, key, v);
              },
      ),
    );
  }
}
