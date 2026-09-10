import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_html/flutter_html.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_client.dart';
import '../../core/theme/vpush_tokens.dart';
import '../../platform/external_links.dart';
import 'news_controller.dart';
import 'news_models.dart';

class NewsPage extends StatefulWidget {
  const NewsPage({super.key, required this.api});

  final ApiClient api;

  @override
  State<NewsPage> createState() => _NewsPageState();
}

class _NewsPageState extends State<NewsPage> {
  late final NewsController _controller = NewsController(api: widget.api);
  final _query = TextEditingController();
  Timer? _searchTimer;

  @override
  void initState() {
    super.initState();
    _controller.load();
  }

  @override
  void dispose() {
    _searchTimer?.cancel();
    _controller.dispose();
    _query.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: _controller,
    builder: (context, child) {
      if (_controller.isLoading && _controller.items.isEmpty) {
        return const Center(child: CircularProgressIndicator());
      }
      if (_controller.error != null && _controller.items.isEmpty) {
        return _ErrorState(
          message: _controller.error!,
          onRetry: _controller.load,
        );
      }
      return RefreshIndicator(
        onRefresh: _controller.load,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(
            VPushTokens.pagePadding,
            12,
            VPushTokens.pagePadding,
            28,
          ),
          children: [
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _query,
                    onChanged: _search,
                    decoration: const InputDecoration(
                      hintText: '搜索标题或摘要',
                      prefixIcon: Icon(Icons.search),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                IconButton(
                  tooltip: '选择来源',
                  onPressed: () => _showSources(context),
                  icon: const Icon(Icons.tune_outlined),
                ),
              ],
            ),
            if (_controller.sources.isNotEmpty) ...[
              const SizedBox(height: 10),
              DropdownButtonFormField<int?>(
                initialValue: _controller.sourceId,
                decoration: const InputDecoration(labelText: '新闻来源'),
                items: [
                  const DropdownMenuItem<int?>(
                    value: null,
                    child: Text('全部来源'),
                  ),
                  ..._controller.sources
                      .where((source) => source.selected)
                      .map(
                        (source) => DropdownMenuItem<int?>(
                          value: source.id,
                          child: Text(source.name),
                        ),
                      ),
                ],
                onChanged: _controller.setSource,
              ),
            ],
            const SizedBox(height: 12),
            if (_controller.items.isEmpty)
              const Padding(
                padding: EdgeInsets.all(32),
                child: Center(child: Text('还没有符合条件的财经新闻')),
              )
            else
              ..._controller.items.map((item) => _NewsCard(item: item)),
            if (_controller.hasMore)
              Padding(
                padding: const EdgeInsets.all(16),
                child: OutlinedButton(
                  onPressed: () => _controller.loadArticles(),
                  child: const Text('加载更多'),
                ),
              ),
          ],
        ),
      );
    },
  );

  void _search(String value) {
    _searchTimer?.cancel();
    _searchTimer = Timer(const Duration(milliseconds: 250), () {
      _controller.query = value;
      _controller.loadArticles(reset: true);
    });
  }

  Future<void> _showSources(BuildContext context) async {
    final selected = _controller.sources
        .where((source) => source.selected)
        .map((source) => source.id)
        .toSet();
    final result = await showModalBottomSheet<Set<int>>(
      context: context,
      showDragHandle: true,
      builder: (context) => StatefulBuilder(
        builder: (context, setModalState) => Padding(
          padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('我的来源', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              ..._controller.sources.map(
                (source) => CheckboxListTile(
                  value: selected.contains(source.id),
                  title: Text(source.name),
                  subtitle: source.enabled ? null : const Text('管理员已暂停更新'),
                  onChanged: source.enabled
                      ? (value) {
                          setModalState(() {
                            if (value == true) {
                              selected.add(source.id);
                            } else {
                              selected.remove(source.id);
                            }
                          });
                        }
                      : null,
                ),
              ),
              FilledButton(
                onPressed: () => Navigator.pop(context, selected),
                child: const Text('保存'),
              ),
            ],
          ),
        ),
      ),
    );
    if (result != null && await _controller.saveSources(result) && mounted) {
      await _controller.load();
    }
  }
}

class NewsArticlePage extends StatefulWidget {
  const NewsArticlePage({
    super.key,
    required this.api,
    required this.articleId,
  });

  final ApiClient api;
  final int articleId;

  @override
  State<NewsArticlePage> createState() => _NewsArticlePageState();
}

class _NewsArticlePageState extends State<NewsArticlePage> {
  late final NewsController _controller = NewsController(api: widget.api);

  @override
  void initState() {
    super.initState();
    _controller.openArticle(widget.articleId);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: _controller,
    builder: (context, child) {
      if (_controller.error != null) {
        return _ErrorState(
          message: _controller.error!,
          onRetry: () => _controller.openArticle(widget.articleId),
        );
      }
      final article = _controller.article;
      if (article == null) {
        return const Center(child: CircularProgressIndicator());
      }
      return CustomScrollView(
        slivers: [
          SliverAppBar(
            pinned: true,
            leading: IconButton(
              tooltip: '返回',
              onPressed: () => context.pop(),
              icon: const Icon(Icons.arrow_back),
            ),
            title: const Text('财经新闻'),
            actions: [
              if (article.url.isNotEmpty)
                IconButton(
                  tooltip: '打开原文',
                  onPressed: () => ExternalLinks.open(article.url),
                  icon: const Icon(Icons.open_in_new),
                ),
            ],
          ),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(18, 20, 18, 8),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    article.title,
                    style: Theme.of(context).textTheme.displaySmall,
                  ),
                  const SizedBox(height: 8),
                  Text(
                    '${article.sourceName} · ${article.publishedAt}',
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                  if (article.author != null)
                    Text(
                      '作者：${article.author}',
                      style: Theme.of(context).textTheme.bodyMedium,
                    ),
                ],
              ),
            ),
          ),
          SliverToBoxAdapter(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(12, 4, 12, 32),
              child: Html(
                data: _articleHtml(article.id, article.contentHtml),
                extensions: [
                  ImageExtension(
                    networkHeaders: widget.api.session.token == null
                        ? const {}
                        : {
                            'Authorization':
                                'Bearer ${widget.api.session.token}',
                          },
                  ),
                ],
              ),
            ),
          ),
        ],
      );
    },
  );

  String _articleHtml(int articleId, String html) => html.replaceAllMapped(
    RegExp(
      r'''<img\b([^>]*?)data-news-image-index=["'](\d+)["']([^>]*)>''',
      caseSensitive: false,
    ),
    (match) {
      final attributes = '${match.group(1)}${match.group(3)}';
      final withoutSrc = attributes.replaceAll(
        RegExp(r'''\bsrc=["'][^"']*["']''', caseSensitive: false),
        '',
      );
      return '<img$withoutSrc src="/api/news/$articleId/images/${match.group(2)}">';
    },
  );
}

class _NewsCard extends StatelessWidget {
  const _NewsCard({required this.item});

  final NewsItem item;

  @override
  Widget build(BuildContext context) => Card(
    margin: const EdgeInsets.only(bottom: 10),
    elevation: 0,
    shape: RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(VPushTokens.radius),
      side: BorderSide(color: Theme.of(context).dividerColor),
    ),
    child: InkWell(
      borderRadius: BorderRadius.circular(VPushTokens.radius),
      onTap: () => context.push('/news/${item.id}'),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    item.sourceName,
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                ),
                Text(
                  item.publishedAt,
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              ],
            ),
            const SizedBox(height: 7),
            Text(item.title, style: Theme.of(context).textTheme.titleMedium),
            if (item.summary.isNotEmpty) ...[
              const SizedBox(height: 5),
              Text(
                item.summary,
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.bodyMedium,
              ),
            ],
            if (item.isNew) ...[
              const SizedBox(height: 8),
              Text(
                '新',
                style: TextStyle(
                  color: Theme.of(context).colorScheme.primary,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ],
        ),
      ),
    ),
  );
}

class _ErrorState extends StatelessWidget {
  const _ErrorState({required this.message, required this.onRetry});

  final String message;
  final Future<void> Function() onRetry;

  @override
  Widget build(BuildContext context) => Center(
    child: Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Text(message),
        const SizedBox(height: 12),
        OutlinedButton(onPressed: onRetry, child: const Text('重试')),
      ],
    ),
  );
}
