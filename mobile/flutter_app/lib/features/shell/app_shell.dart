import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/session_store.dart';
import '../../core/theme/theme_controller.dart';
import '../../core/theme/vpush_motion.dart';
import '../../core/theme/vpush_tokens.dart';

class AppShell extends StatefulWidget {
  const AppShell({
    super.key,
    required this.child,
    required this.location,
    required this.session,
    required this.themeController,
  });

  final Widget child;
  final String location;
  final SessionStore session;
  final ThemeController themeController;

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  final _bottomNav = BottomNavVisibility();

  @override
  void didUpdateWidget(covariant AppShell oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.location != widget.location) {
      _bottomNav.reset();
    }
  }

  bool _onScroll(ScrollNotification notification) {
    if (notification is! ScrollUpdateNotification) return false;
    final metrics = notification.metrics;
    final oldVisible = _bottomNav.visible;
    _bottomNav.update(
      pixels: metrics.pixels,
      maxScrollExtent: metrics.maxScrollExtent,
    );
    if (oldVisible != _bottomNav.visible) setState(() {});
    return false;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final selected = _selectedIndex(widget.location);
    final bottomNavVisible = _bottomNav.visible;
    final reduceMotion = MediaQuery.of(context).disableAnimations;
    return Scaffold(
      appBar: AppBar(
        title: Text(_titleFor(widget.location)),
        actions: [
          IconButton(
            tooltip: '切换主题',
            onPressed: () =>
                widget.themeController.toggle(Theme.of(context).brightness),
            icon: Icon(
              Theme.of(context).brightness == Brightness.dark
                  ? Icons.light_mode_outlined
                  : Icons.dark_mode_outlined,
            ),
          ),
          IconButton(
            tooltip: '退出登录',
            onPressed: () async {
              await widget.session.clear();
              if (context.mounted) context.go('/login');
            },
            icon: const Icon(Icons.logout_outlined),
          ),
        ],
      ),
      body: NotificationListener<ScrollNotification>(
        onNotification: _onScroll,
        child: widget.child,
      ),
      bottomNavigationBar: IgnorePointer(
        ignoring: !bottomNavVisible,
        child: SafeArea(
          top: false,
          child: AnimatedSlide(
            offset: bottomNavVisible ? Offset.zero : const Offset(0, 1),
            duration: reduceMotion
                ? Duration.zero
                : VPushMotion.bottomNavigation,
            curve: VPushMotion.standardCurve,
            child: Container(
              height: VPushTokens.bottomNavHeight,
              decoration: BoxDecoration(
                color: theme.scaffoldBackgroundColor,
                border: Border(top: BorderSide(color: theme.dividerColor)),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceAround,
                children: [
                  _NavButton(
                    selected: selected == 0,
                    icon: Icons.view_stream_outlined,
                    label: '动态',
                    onTap: () => context.go('/timeline'),
                  ),
                  if (widget.session.newsVisible)
                    _NavButton(
                      selected: selected == 1,
                      icon: Icons.article_outlined,
                      label: '财经新闻',
                      onTap: () => context.go('/news'),
                    ),
                  _NavButton(
                    selected: selected == 2,
                    icon: Icons.grid_view_outlined,
                    label: '广场',
                    onTap: () => context.go('/home'),
                  ),
                  _NavButton(
                    selected: selected == 3,
                    icon: Icons.settings_outlined,
                    label: '个人设置',
                    onTap: () => context.go('/settings'),
                  ),
                  if (widget.session.isAdmin)
                    _NavButton(
                      selected: selected == 4,
                      icon: Icons.more_horiz,
                      label: '更多',
                      onTap: () => context.go('/more'),
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  int _selectedIndex(String location) {
    if (location.startsWith('/news')) return widget.session.newsVisible ? 1 : 0;
    if (location.startsWith('/home') || location.startsWith('/kol')) {
      return widget.session.newsVisible ? 2 : 1;
    }
    if (location.startsWith('/settings')) {
      return widget.session.newsVisible ? 3 : 2;
    }
    if (location.startsWith('/more') || location.startsWith('/admin')) {
      return widget.session.newsVisible ? 4 : 3;
    }
    return 0;
  }

  String _titleFor(String location) {
    if (location.startsWith('/news')) return '财经新闻';
    if (location.startsWith('/home') || location.startsWith('/kol')) {
      return '订阅广场';
    }
    if (location.startsWith('/settings')) return '个人设置';
    if (location.startsWith('/knowledge')) return '研报中心';
    if (location.startsWith('/more')) return '更多';
    if (location.startsWith('/admin')) return '管理';
    return '动态';
  }
}

class BottomNavVisibility {
  bool visible = true;
  double _lastPixels = 0;
  double _travel = 0;

  void reset() {
    visible = true;
    _lastPixels = 0;
    _travel = 0;
  }

  void update({required double pixels, required double maxScrollExtent}) {
    final clamped = pixels.clamp(0.0, maxScrollExtent).toDouble();
    final delta = clamped - _lastPixels;
    _lastPixels = clamped;
    if (maxScrollExtent <= 0 || clamped <= 0) {
      _travel = 0;
      visible = true;
      return;
    }
    if (delta == 0) return;
    _travel = delta.sign == _travel.sign ? _travel + delta : delta;
    if (_travel >= 24 && visible) {
      _travel = 0;
      visible = false;
    } else if (_travel <= -8 && !visible) {
      _travel = 0;
      visible = true;
    }
  }
}

class _NavButton extends StatelessWidget {
  const _NavButton({
    required this.selected,
    required this.icon,
    required this.label,
    required this.onTap,
  });

  final bool selected;
  final IconData icon;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = selected
        ? Theme.of(context).colorScheme.primary
        : Theme.of(context).hintColor;
    return Expanded(
      child: Semantics(
        label: label,
        button: true,
        selected: selected,
        child: Tooltip(
          message: label,
          child: IconButton(
            onPressed: onTap,
            color: color,
            iconSize: 24,
            icon: Icon(icon),
          ),
        ),
      ),
    );
  }
}
