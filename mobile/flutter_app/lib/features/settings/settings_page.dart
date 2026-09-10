import 'package:flutter/material.dart';

import '../../core/widgets/vpush_page.dart';

class SettingsPage extends StatelessWidget {
  const SettingsPage({super.key});

  @override
  Widget build(BuildContext context) => const VPushPage(
    title: '个人设置',
    description: '管理推送渠道、免打扰、关键词和账号。',
    icon: Icons.settings_outlined,
  );
}
