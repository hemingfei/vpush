import 'package:flutter/material.dart';

import '../../core/widgets/vpush_page.dart';

class KnowledgePage extends StatelessWidget {
  const KnowledgePage({super.key});

  @override
  Widget build(BuildContext context) => const VPushPage(
    title: '研报中心',
    description: '搜索、阅读和跟随已授权的研究文档。',
    icon: Icons.menu_book_outlined,
  );
}
