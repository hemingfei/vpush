import 'package:flutter/material.dart';

import '../../core/widgets/vpush_page.dart';

class TimelinePage extends StatelessWidget {
  const TimelinePage({super.key});

  @override
  Widget build(BuildContext context) => const VPushPage(
    title: '动态',
    description: '查看已订阅大 V 的最新动态与实时快讯。',
    icon: Icons.view_stream_outlined,
  );
}
