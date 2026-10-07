/// Register screen — real auth flow (Phase 3B).
///
/// Wires the form to [AuthNotifier.register]. Auto-login on success (backend
/// returns tokens). Shows loading + mapped errors. Stays within Phase 3A
/// layout/typography/Design Tokens.
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../../app/theme/colors.dart';
import '../../../app/theme/typography.dart';
import '../auth_notifier.dart';

class RegisterPage extends StatefulWidget {
  const RegisterPage({super.key});

  @override
  State<RegisterPage> createState() => _RegisterPageState();
}

class _RegisterPageState extends State<RegisterPage> {
  final _username = TextEditingController();
  final _phone = TextEditingController();
  final _password = TextEditingController();
  final _nickname = TextEditingController();

  @override
  void dispose() {
    _username.dispose();
    _phone.dispose();
    _password.dispose();
    _nickname.dispose();
    super.dispose();
  }

  Future<void> _submit(AuthNotifier auth) async {
    await auth.register(
      username: _username.text,
      phone: _phone.text,
      password: _password.text,
      nickname: _nickname.text.isEmpty ? _username.text : _nickname.text,
    );
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthNotifier>();

    return Scaffold(
      backgroundColor: AppColors.bg,
      appBar: AppBar(title: const Text('注册')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          TextField(
            controller: _username,
            enabled: !auth.loading,
            decoration: const InputDecoration(labelText: '用户名'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _phone,
            enabled: !auth.loading,
            keyboardType: TextInputType.phone,
            decoration: const InputDecoration(labelText: '手机号'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _nickname,
            enabled: !auth.loading,
            decoration: const InputDecoration(labelText: '昵称（可选）'),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _password,
            enabled: !auth.loading,
            obscureText: true,
            decoration: const InputDecoration(labelText: '密码'),
          ),
          const SizedBox(height: 16),
          if (auth.error != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Text(
                auth.error!.message,
                style: AppTypography.caption.copyWith(color: AppColors.error),
              ),
            ),
          ElevatedButton(
            onPressed: auth.loading ? null : () => _submit(auth),
            child: auth.loading
                ? const SizedBox(
                    height: 16,
                    width: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Text('创建账号'),
          ),
          const SizedBox(height: 12),
          Text(
            '注册即代表同意用户协议与隐私政策',
            style: AppTypography.caption,
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}
