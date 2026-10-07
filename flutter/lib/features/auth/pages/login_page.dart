/// Login screen — real auth flow (Phase 3B).
///
/// Wires the form to [AuthNotifier.login]. Shows loading state and maps
/// errors via the notifier's [AuthError] (never raw DioException). Stays
/// within the Phase 3A layout/typography/Design Tokens.
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';

import '../../../app/theme/colors.dart';
import '../../../app/theme/typography.dart';
import '../auth_notifier.dart';

class LoginPage extends StatefulWidget {
  const LoginPage({super.key});

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  final _identifier = TextEditingController();
  final _password = TextEditingController();

  @override
  void dispose() {
    _identifier.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit(AuthNotifier auth) async {
    await auth.login(identifier: _identifier.text, password: _password.text);
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthNotifier>();

    return Scaffold(
      backgroundColor: AppColors.bg,
      body: Center(
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 320),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('登录', style: AppTypography.h1),
              const SizedBox(height: 4),
              Text('安静、可靠的私人通讯', style: AppTypography.body2),
              const SizedBox(height: 24),
              TextField(
                controller: _identifier,
                enabled: !auth.loading,
                decoration: const InputDecoration(labelText: '用户名 / 手机号'),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _password,
                enabled: !auth.loading,
                obscureText: true,
                decoration: const InputDecoration(labelText: '密码'),
                onSubmitted: (_) => _submit(auth),
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
                    : const Text('登录'),
              ),
              const SizedBox(height: 12),
              TextButton(
                onPressed: auth.loading
                    ? null
                    : () => context.push('/forgot'),
                child: const Text('忘记密码？'),
              ),
              TextButton(
                onPressed: auth.loading
                    ? null
                    : () => context.push('/register'),
                child: const Text('没有账号？注册'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
