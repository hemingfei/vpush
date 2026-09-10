import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_client.dart';
import '../../core/session_store.dart';
import '../../core/theme/theme_controller.dart';
import '../../core/theme/vpush_motion.dart';
import 'auth_controller.dart';

class AuthPage extends StatefulWidget {
  const AuthPage({
    super.key,
    required this.api,
    required this.session,
    required this.themeController,
    this.register = false,
  });

  final ApiClient api;
  final SessionStore session;
  final ThemeController themeController;
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
    return Scaffold(
      body: Stack(
        children: [
          const Positioned.fill(child: _LoginBackground()),
          SafeArea(
            child: Align(
              alignment: Alignment.topRight,
              child: Padding(
                padding: const EdgeInsets.only(right: 12, top: 2),
                child: IconButton(
                  tooltip: '切换主题',
                  onPressed: () => widget.themeController.toggle(
                    MediaQuery.platformBrightnessOf(context),
                  ),
                  icon: Icon(
                    Theme.of(context).brightness == Brightness.dark
                        ? Icons.light_mode_outlined
                        : Icons.dark_mode_outlined,
                  ),
                ),
              ),
            ),
          ),
          SafeArea(
            child: LayoutBuilder(
              builder: (context, constraints) {
                final wide = constraints.maxWidth > 900;
                return SingleChildScrollView(
                  padding: EdgeInsets.fromLTRB(
                    wide ? 24 : 16,
                    56,
                    wide ? 24 : 16,
                    32,
                  ),
                  child: Center(
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 980),
                      child: wide
                          ? Row(
                              crossAxisAlignment: CrossAxisAlignment.center,
                              children: [
                                const Expanded(child: _LoginBrand()),
                                const SizedBox(width: 64),
                                Expanded(child: _buildCard(context)),
                              ],
                            )
                          : Column(
                              children: [
                                const _LoginBrand(),
                                const SizedBox(height: 32),
                                _buildCard(context),
                              ],
                            ),
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCard(BuildContext context) {
    final theme = Theme.of(context);
    return AnimatedSwitcher(
      duration: VPushMotion.loginCard,
      switchInCurve: VPushMotion.enterCurve,
      child: Container(
        key: ValueKey(_register),
        width: double.infinity,
        padding: const EdgeInsets.symmetric(horizontal: 22, vertical: 28),
        decoration: BoxDecoration(
          color: theme.colorScheme.surface,
          borderRadius: BorderRadius.circular(20),
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
              _AuthSwitch(
                register: _register,
                enabled: !_controller.isBusy,
                onChanged: (value) => setState(() => _register = value),
              ),
              const SizedBox(height: 2),
              AnimatedSwitcher(
                duration: const Duration(milliseconds: 160),
                switchInCurve: VPushMotion.formCurve,
                child: _register
                    ? _buildRegisterForm(theme)
                    : _buildLoginForm(theme),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildLoginForm(ThemeData theme) => Column(
    key: const ValueKey('login-form'),
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Text('欢迎回来', style: theme.textTheme.titleMedium),
      const SizedBox(height: 6),
      Text('回到你的订阅流，继续接收大V动态。', style: theme.textTheme.bodyMedium),
      const SizedBox(height: 22),
      const _FieldLabel(text: '用户名'),
      _input(
        controller: _username,
        hintText: '输入用户名',
        autofillHints: const [AutofillHints.username],
        textInputAction: TextInputAction.next,
      ),
      const SizedBox(height: 2),
      const _FieldLabel(text: '密码'),
      _passwordInput(hintText: '输入密码'),
      _errorText(theme),
      _submitButton(label: '登 录'),
    ],
  );

  Widget _buildRegisterForm(ThemeData theme) => Column(
    key: const ValueKey('register-form'),
    crossAxisAlignment: CrossAxisAlignment.stretch,
    children: [
      Text('创建账号', style: theme.textTheme.titleMedium),
      const SizedBox(height: 6),
      Text('注册后即可自选大V，开启订阅推送。', style: theme.textTheme.bodyMedium),
      const SizedBox(height: 22),
      const _FieldLabel(text: '用户名'),
      _input(
        controller: _username,
        hintText: '6-30 位，字母或中文开头',
        autofillHints: const [AutofillHints.newUsername],
        textInputAction: TextInputAction.next,
      ),
      const SizedBox(height: 2),
      const _FieldLabel(text: '密码'),
      _passwordInput(hintText: '至少 6 位字符'),
      const SizedBox(height: 2),
      const _FieldLabel(text: '邀请码'),
      _input(
        controller: _code,
        hintText: '向管理员索取注册邀请码',
        textInputAction: TextInputAction.done,
        onSubmitted: (_) => _submit(),
      ),
      _errorText(theme),
      _submitButton(label: '创建账号'),
    ],
  );

  Widget _input({
    required TextEditingController controller,
    required String hintText,
    Iterable<String>? autofillHints,
    TextInputAction? textInputAction,
    ValueChanged<String>? onSubmitted,
  }) {
    return SizedBox(
      height: 42,
      child: TextField(
        controller: controller,
        enabled: !_controller.isBusy,
        textInputAction: textInputAction,
        autofillHints: autofillHints,
        onSubmitted: onSubmitted,
        decoration: InputDecoration(hintText: hintText),
      ),
    );
  }

  Widget _passwordInput({required String hintText}) {
    return SizedBox(
      height: 42,
      child: TextField(
        controller: _password,
        enabled: !_controller.isBusy,
        obscureText: _obscurePassword,
        textInputAction: _register
            ? TextInputAction.next
            : TextInputAction.done,
        autofillHints: [
          _register ? AutofillHints.newPassword : AutofillHints.password,
        ],
        onSubmitted: (_) => _register ? null : _submit(),
        decoration: InputDecoration(
          hintText: hintText,
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
    );
  }

  Widget _errorText(ThemeData theme) {
    return SizedBox(
      height: _controller.error == null ? 30 : 42,
      child: _controller.error == null
          ? null
          : Padding(
              padding: const EdgeInsets.only(top: 10, bottom: 8),
              child: Text(
                _controller.error!,
                style: TextStyle(color: theme.colorScheme.error, fontSize: 13),
              ),
            ),
    );
  }

  Widget _submitButton({required String label}) {
    return SizedBox(
      height: 42,
      child: FilledButton(
        onPressed: _controller.isBusy ? null : _submit,
        child: _controller.isBusy
            ? const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : Text(label),
      ),
    );
  }
}

class _LoginBrand extends StatelessWidget {
  const _LoginBrand();

  @override
  Widget build(BuildContext context) {
    final centered = MediaQuery.sizeOf(context).width <= 900;
    return Column(
      crossAxisAlignment: centered
          ? CrossAxisAlignment.center
          : CrossAxisAlignment.start,
      children: [
        SvgPicture.asset(
          'assets/brand/logo-mark.svg',
          width: 60,
          height: 60,
          semanticsLabel: 'VPush',
        ),
        const SizedBox(height: 16),
        Text(
          'VPush',
          style: Theme.of(context).textTheme.displaySmall?.copyWith(
            fontSize: 30,
            fontWeight: FontWeight.w600,
            height: 1.15,
          ),
        ),
        const SizedBox(height: 8),
        Text(
          '大V动态聚合分发 · 私有通知值班台',
          style: Theme.of(context).textTheme.bodyLarge?.copyWith(
            color: Theme.of(context).colorScheme.onSurface
                .withValues(alpha: .62),
          ),
          textAlign: centered ? TextAlign.center : TextAlign.start,
        ),
        const SizedBox(height: 24),
        const _LoginFeatures(),
      ],
    );
  }
}

class _LoginFeatures extends StatelessWidget {
  const _LoginFeatures();

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 400),
      child: const Column(
        children: [
          _LoginFeature(
            icon: Icons.format_list_bulleted,
            title: '多源动态聚合',
            detail: '聚合雪球 / 微博 / X 大V动态',
          ),
          SizedBox(height: 12),
          _LoginFeature(
            icon: Icons.send_outlined,
            title: '全渠道即时分发',
            detail: '新帖推到 Telegram / 飞书 / Bark / 浏览器',
          ),
          SizedBox(height: 12),
          _LoginFeature(
            icon: Icons.shield_outlined,
            title: '自托管私有自治',
            detail: '自托管部署，订阅数据完全私有',
          ),
        ],
      ),
    );
  }
}

class _LoginFeature extends StatelessWidget {
  const _LoginFeature({
    required this.icon,
    required this.title,
    required this.detail,
  });

  final IconData icon;
  final String title;
  final String detail;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        border: Border.all(color: theme.dividerColor),
        borderRadius: BorderRadius.circular(14),
        boxShadow: const [
          BoxShadow(
            color: Color(0x0A0F172A),
            blurRadius: 10,
            offset: Offset(0, 2),
          ),
        ],
      ),
      child: Row(
        children: [
          Container(
            width: 36,
            height: 36,
            decoration: BoxDecoration(
              color: theme.colorScheme.onSurface.withValues(alpha: .04),
              border: Border.all(
                color: theme.colorScheme.onSurface.withValues(alpha: .06),
              ),
              borderRadius: BorderRadius.circular(10),
            ),
            child: Icon(icon, size: 18, color: theme.colorScheme.primary),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Flexible(
                      child: Text(
                        title,
                        style: theme.textTheme.labelLarge,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Container(
                      width: 6,
                      height: 6,
                      decoration: const BoxDecoration(
                        color: Color(0xFF10B981),
                        shape: BoxShape.circle,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 2),
                Text(
                  detail,
                  style: theme.textTheme.bodyMedium?.copyWith(fontSize: 12),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _AuthSwitch extends StatelessWidget {
  const _AuthSwitch({
    required this.register,
    required this.enabled,
    required this.onChanged,
  });

  final bool register;
  final bool enabled;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        padding: const EdgeInsets.all(3),
        decoration: BoxDecoration(
          color: theme.colorScheme.onSurface.withValues(alpha: .05),
          borderRadius: BorderRadius.circular(999),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            _tab(context, label: '登录', active: !register, value: false),
            _tab(context, label: '注册', active: register, value: true),
          ],
        ),
      ),
    );
  }

  Widget _tab(
    BuildContext context, {
    required String label,
    required bool active,
    required bool value,
  }) {
    final theme = Theme.of(context);
    return Semantics(
      button: true,
      selected: active,
      label: label,
      child: InkWell(
        onTap: enabled ? () => onChanged(value) : null,
        borderRadius: BorderRadius.circular(999),
        child: AnimatedContainer(
          duration: VPushMotion.standard,
          constraints: const BoxConstraints(minWidth: 66, minHeight: 42),
          padding: const EdgeInsets.symmetric(horizontal: 16),
          alignment: Alignment.center,
          decoration: BoxDecoration(
            color: active ? theme.colorScheme.surface : Colors.transparent,
            borderRadius: BorderRadius.circular(999),
            boxShadow: active
                ? const [
                    BoxShadow(
                      color: Color(0x0A0F172A),
                      blurRadius: 10,
                      offset: Offset(0, 2),
                    ),
                  ]
                : null,
          ),
          child: Text(
            label,
            style: theme.textTheme.bodyMedium?.copyWith(
              color: active ? theme.colorScheme.onSurface : null,
              fontWeight: active ? FontWeight.w600 : null,
            ),
          ),
        ),
      ),
    );
  }
}

class _FieldLabel extends StatelessWidget {
  const _FieldLabel({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 6),
    child: Text(text, style: Theme.of(context).textTheme.labelLarge),
  );
}

class _LoginBackground extends StatelessWidget {
  const _LoginBackground();

  @override
  Widget build(BuildContext context) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    return CustomPaint(
      painter: _LoginGridPainter(
        lineColor: dark
            ? Colors.white.withValues(alpha: .035)
            : const Color(0x0A0C1222),
      ),
    );
  }
}

class _LoginGridPainter extends CustomPainter {
  const _LoginGridPainter({required this.lineColor});

  final Color lineColor;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = lineColor
      ..strokeWidth = 1;
    for (double x = 0; x <= size.width; x += 32) {
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), paint);
    }
    for (double y = 0; y <= size.height; y += 32) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), paint);
    }
  }

  @override
  bool shouldRepaint(covariant _LoginGridPainter oldDelegate) =>
      oldDelegate.lineColor != lineColor;
}
