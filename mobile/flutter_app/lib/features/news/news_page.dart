import 'package:flutter/material.dart';

import '../../core/widgets/vpush_page.dart';

class NewsPage extends StatelessWidget {
  const NewsPage({super.key});

  @override
  Widget build(BuildContext context) => const VPushPage(
    title: '财经新闻',
    description: '按媒体阅读登录后的财经长文。',
    icon: Icons.article_outlined,
  );
}
