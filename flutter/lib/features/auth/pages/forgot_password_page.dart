/// Forgot Password screen — real flow (Phase 3B).
///
/// Calls [AuthRepository.forgotPassword]. In dev/non-production the backend
/// returns a mock code; we confirm the request succeeded without surfacing
/// internal details. Stays within Phase 3A tokens.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../app/theme/colors.dart';
import '../../../app/theme/typography.dart';
import '../auth_notifier.dart';
import '../repositories/auth_repository.dart';

class ForgotPasswordPage extends StatefulWidget {
  const ForgotPasswordPage({super.key});

  @override
  State<ForgotPasswordPage> createState() => _ForgotPasswordPageState();
}

class _ForgotPasswordPageState extends State<ForgotPasswordPage> {
  final _phone = TextEditingController();
  bool _sent = false;

  @override
  void dispose() {
    _phone.dispose();
    super.dispose();
  }

  Future<void> _submit(AuthNotifier auth, AuthRepository repo) async {
    setState(() => _sent = false);
    try {
      await repo.forgotPassword(_phone.text);
      if (mounted) {
        setState(() => _sent = true);
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('若账号存在，重置码已发送（开发环境见后端日志）')),
        );
      }
    } on Object {
      // Error surfaced by the repository's exception; keep UI minimal.
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthNotifier>();
    final repo = context.read<AuthRepository>();

    return Scaffold(
      backgroundColor: AppColors.bg,
      appBar: AppBar(title: const Text('找回密码')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text('输入注册手机号以接收重置码', style: AppTypography.body2),
          const SizedBox(height: 12),
          TextField(
            controller: _phone,
            enabled: !auth.loading,
            keyboardType: TextInputType.phone,
            decoration: const InputDecoration(labelText: '手机号'),
          ),
          const SizedBox(height: 16),
          if (_sent)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Text('重置码请求已发送', style: AppTypography.body2),
            ),
          ElevatedButton(
            onPressed: auth.loading ? null : () => _submit(auth, repo),
            child: const Text('发送重置码'),
          ),
        ],
      ),
    );
  }
}
