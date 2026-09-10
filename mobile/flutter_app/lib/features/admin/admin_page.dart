import 'package:flutter/material.dart';

import '../../core/widgets/vpush_page.dart';

class AdminPage extends StatelessWidget {
  const AdminPage({super.key, required this.section});

  final String section;

  @override
  Widget build(BuildContext context) => VPushPage(
    title: '管理 · $section',
    description: '管理员功能按 Web 移动端分组逐项迁移。',
    icon: Icons.admin_panel_settings_outlined,
  );
}
