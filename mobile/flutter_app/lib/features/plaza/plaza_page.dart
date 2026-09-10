import 'package:flutter/material.dart';

import '../../core/widgets/vpush_page.dart';

class PlazaPage extends StatelessWidget {
  const PlazaPage({super.key});

  @override
  Widget build(BuildContext context) => const VPushPage(
    title: '订阅广场',
    description: '发现并维护你关注的大 V 与组合。',
    icon: Icons.grid_view_outlined,
  );
}
