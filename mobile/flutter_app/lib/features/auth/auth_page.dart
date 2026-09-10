import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_client.dart';
import '../../core/session_store.dart';
import '../../core/theme/vpush_motion.dart';
import '../../core/theme/vpush_tokens.dart';
import 'auth_controller.dart';

class AuthPage extends StatefulWidget {
  const AuthPage({
    super.key,
    required this.api,
    required this.session,
    this.register = false,
  });

  final ApiClient api;
  final SessionStore session;
  final bool register;

  @override
  State<AuthPage> createState() => _AuthPageState();
}

class _AuthPageState extends State<AuthPage> {
  late bool _register = widget.register;
  late final AuthController _controller = AuthController(
    api: widget.api,
    session: widget.session,
  );
  final _username = TextEditingController();
  final _password = TextEditingController();
  final _code = TextEditingController();
  bool _obscurePassword = true;

  @override
  void dispose() {
    _controller.dispose();
    _username.dispose();
    _password.dispose();
    _code.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    FocusManager.instance.primaryFocus?.unfocus();
    final success = _register
        ? await _controller.register(_username.text, _password.text, _code.text)
        : await _controller.login(_username.text, _password.text);
    if (success && mounted) context.go('/timeline');
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 440),
              child: AnimatedSwitcher(
                duration: VPushMotion.loginCard,
                switchInCurve: VPushMotion.enterCurve,
                child: _buildCard(context, theme),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildCard(BuildContext context, ThemeData theme) {
    return Container(
      key: ValueKey(_register),
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(VPushTokens.cardRadius),
        border: Border.all(color: theme.dividerColor),
        boxShadow: const [
          BoxShadow(
            color: Color(0x140F172A),
            blurRadius: 28,
            offset: Offset(0, 12),
          ),
        ],
      ),
      child: ListenableBuilder(
        listenable: _controller,
        builder: (context, child) => Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('V Push', style: theme.textTheme.displaySmall),
            const SizedBox(height: 6),
            Text(
              _register ? '创建账号，开始接收关注动态' : '可靠、直接的动态送达工具',
              style: theme.textTheme.bodyMedium,
            ),
            const SizedBox(height: 24),
            TextField(
              controller: _username,
              enabled: !_controller.isBusy,
              textInputAction: TextInputAction.next,
              autofillHints: const [AutofillHints.username],
              decoration: const InputDecoration(labelText: '用户名'),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: _password,
              enabled: !_controller.isBusy,
              obscureText: _obscurePassword,
              textInputAction: _register
                  ? TextInputAction.next
                  : TextInputAction.done,
              autofillHints: const [AutofillHints.password],
              onSubmitted: (_) => _register ? null : _submit(),
              decoration: InputDecoration(
                labelText: '密码',
                suffixIcon: IconButton(
                  tooltip: _obscurePassword ? '显示密码' : '隐藏密码',
                  onPressed: () =>
                      setState(() => _obscurePassword = !_obscurePassword),
                  icon: Icon(
                    _obscurePassword
                        ? Icons.visibility_outlined
                        : Icons.visibility_off_outlined,
                  ),
                ),
              ),
            ),
            if (_register) ...[
              const SizedBox(height: 12),
              TextField(
                controller: _code,
                enabled: !_controller.isBusy,
                textInputAction: TextInputAction.done,
                decoration: const InputDecoration(labelText: '邀请码'),
                onSubmitted: (_) => _submit(),
              ),
            ],
            if (_controller.error != null) ...[
              const SizedBox(height: 12),
              Text(
                _controller.error!,
                style: TextStyle(color: theme.colorScheme.error),
              ),
            ],
            const SizedBox(height: 20),
            SizedBox(
              height: VPushTokens.controlHeight,
              child: FilledButton(
                onPressed: _controller.isBusy ? null : _submit,
                child: _controller.isBusy
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : Text(_register ? '注册' : '登录'),
              ),
            ),
            const SizedBox(height: 8),
            TextButton(
              onPressed: _controller.isBusy
                  ? null
                  : () => setState(() => _register = !_register),
              child: Text(_register ? '已有账号，返回登录' : '没有账号，使用邀请码注册'),
            ),
          ],
        ),
      ),
    );
  }
}
