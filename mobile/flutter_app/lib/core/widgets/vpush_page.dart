import 'package:flutter/material.dart';

import '../theme/vpush_tokens.dart';

class VPushPage extends StatelessWidget {
  const VPushPage({
    super.key,
    required this.title,
    required this.description,
    this.icon = Icons.hourglass_empty_outlined,
  });

  final String title;
  final String description;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.fromLTRB(
        VPushTokens.pagePadding,
        16,
        VPushTokens.pagePadding,
        32,
      ),
      children: [
        Text(title, style: theme.textTheme.displaySmall),
        const SizedBox(height: 8),
        Text(description, style: theme.textTheme.bodyMedium),
        const SizedBox(height: 20),
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: theme.colorScheme.surface,
            borderRadius: BorderRadius.circular(VPushTokens.cardRadius),
            border: Border.all(color: theme.dividerColor),
          ),
          child: Column(
            children: [
              Icon(icon, size: 28, color: theme.colorScheme.primary),
              const SizedBox(height: 12),
              Text('正在接入 Web 移动版能力', style: theme.textTheme.titleMedium),
              const SizedBox(height: 6),
              Text(
                '页面路由和应用壳层已就绪，功能会按对照矩阵逐项接入。',
                textAlign: TextAlign.center,
                style: theme.textTheme.bodyMedium,
              ),
            ],
          ),
        ),
      ],
    );
  }
}
