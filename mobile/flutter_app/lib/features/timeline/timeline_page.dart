import 'dart:async';

import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/theme/vpush_tokens.dart';
import '../../platform/external_links.dart';
import '../../platform/file_actions.dart';
import 'timeline_controller.dart';
import 'timeline_models.dart';
import 'market_controller.dart';

class TimelinePage extends StatefulWidget {
  const TimelinePage({super.key, required this.api});

  final ApiClient api;

  @override
  State<TimelinePage> createState() => _TimelinePageState();
}

class _TimelinePageState extends State<TimelinePage>
    with WidgetsBindingObserver {
  late final TimelineController _controller = TimelineController(
    api: widget.api,
  );
  late final MarketController _market = MarketController(api: widget.api);
  final _query = TextEditingController();
  Timer? _pollTimer;
  bool _loadMoreScheduled = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _controller.load();
    _market
      ..load()
      ..startPolling();
    _pollTimer = Timer.periodic(const Duration(seconds: 60), (_) {
      _controller.poll();
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _pollTimer?.cancel();
    _controller.dispose();
    _market.dispose();
    _query.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _market.startPolling();
      _pollTimer ??= Timer.periodic(const Duration(seconds: 60), (_) {
        _controller.poll();
      });
      _controller.poll();
    } else if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.detached) {
      _pollTimer?.cancel();
      _pollTimer = null;
      _market.stopPolling();
    }
  }

  Future<void> _applyQuery(String value) async {
    _controller.query = value.trim();
    await _controller.load();
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: _controller,
      builder: (context, child) {
        final theme = Theme.of(context);
        return RefreshIndicator(
          onRefresh: _controller.refresh,
          child: CustomScrollView(
            slivers: [
              SliverToBoxAdapter(child: _buildToolbar(context)),
              SliverToBoxAdapter(child: MarketPanel(controller: _market)),
              if (_controller.isLoading && _controller.posts.isEmpty)
                const SliverFillRemaining(
                  hasScrollBody: false,
                  child: Center(child: CircularProgressIndicator()),
                )
              else if (_controller.error != null && _controller.posts.isEmpty)
                SliverFillRemaining(
                  hasScrollBody: false,
                  child: _ErrorState(
                    message: _controller.error!,
                    onRetry: _controller.refresh,
                  ),
                )
              else if (_controller.posts.isEmpty)
                const SliverFillRemaining(
                  hasScrollBody: false,
                  child: _EmptyState(),
                )
              else
                SliverPadding(
                  padding: const EdgeInsets.fromLTRB(
                    VPushTokens.pagePadding,
                    4,
                    VPushTokens.pagePadding,
                    24,
                  ),
                  sliver: SliverList.builder(
                    itemCount:
                        _controller.posts.length +
                        (_controller.hasMore ? 1 : 0),
                    itemBuilder: (context, index) {
                      if (index == _controller.posts.length) {
                        _scheduleLoadMore();
                        return const Padding(
                          padding: EdgeInsets.all(16),
                          child: Center(
                            child: CircularProgressIndicator(strokeWidth: 2),
                          ),
                        );
                      }
                      return _PostCard(
                        api: widget.api,
                        post: _controller.posts[index],
                      );
                    },
                  ),
                ),
              if (_controller.error != null && _controller.posts.isNotEmpty)
                SliverToBoxAdapter(
                  child: Padding(
                    padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
                    child: Text(
                      _controller.error!,
                      style: TextStyle(color: theme.colorScheme.error),
                    ),
                  ),
                ),
            ],
          ),
        );
      },
    );
  }

  void _scheduleLoadMore() {
    if (_loadMoreScheduled) return;
    _loadMoreScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadMoreScheduled = false;
      if (mounted) _controller.load(reset: false);
    });
  }

  Widget _buildToolbar(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        VPushTokens.pagePadding,
        12,
        VPushTokens.pagePadding,
        8,
      ),
      child: Column(
        children: [
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _query,
                  textInputAction: TextInputAction.search,
                  onSubmitted: _applyQuery,
                  decoration: const InputDecoration(
                    hintText: '搜索动态',
                    prefixIcon: Icon(Icons.search),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              Semantics(
                label: '实时快讯',
                child: Switch(
                  value: _controller.isLive,
                  onChanged: _controller.setLive,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              _FilterButton(
                label: '全部',
                selected: _controller.platform.isEmpty,
                onPressed: () => _setPlatform(''),
              ),
              _FilterButton(
                label: '雪球',
                selected: _controller.platform == 'xueqiu',
                onPressed: () => _setPlatform('xueqiu'),
              ),
              _FilterButton(
                label: '微博',
                selected: _controller.platform == 'weibo',
                onPressed: () => _setPlatform('weibo'),
              ),
              _FilterButton(
                label: 'X',
                selected: _controller.platform == 'twitter',
                onPressed: () => _setPlatform('twitter'),
              ),
              const Spacer(),
              IconButton(
                tooltip: '特别关注',
                onPressed: () async {
                  _controller.favoriteOnly = !_controller.favoriteOnly;
                  await _controller.load();
                },
                icon: Icon(
                  _controller.favoriteOnly ? Icons.star : Icons.star_border,
                ),
                color: _controller.favoriteOnly
                    ? Theme.of(context).colorScheme.primary
                    : null,
              ),
            ],
          ),
        ],
      ),
    );
  }

  Future<void> _setPlatform(String value) async {
    _controller.platform = value;
    await _controller.load();
  }
}

class _FilterButton extends StatelessWidget {
  const _FilterButton({
    required this.label,
    required this.selected,
    required this.onPressed,
  });

  final String label;
  final bool selected;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(right: 6),
      child: OutlinedButton(
        onPressed: onPressed,
        style: OutlinedButton.styleFrom(
          minimumSize: const Size(0, 36),
          padding: const EdgeInsets.symmetric(horizontal: 12),
          foregroundColor: selected ? Colors.white : null,
          backgroundColor: selected
              ? Theme.of(context).colorScheme.primary
              : null,
          side: BorderSide(
            color: selected
                ? Theme.of(context).colorScheme.primary
                : Theme.of(context).dividerColor,
          ),
        ),
        child: Text(label),
      ),
    );
  }
}

class _PostCard extends StatefulWidget {
  const _PostCard({required this.api, required this.post});

  final ApiClient api;
  final TimelinePost post;

  @override
  State<_PostCard> createState() => _PostCardState();
}

class _PostCardState extends State<_PostCard> {
  bool _expanded = false;
  bool _showOriginal = false;
  bool _downloading = false;

  TimelinePost get post => widget.post;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final source = _showOriginal && post.contentSource.isNotEmpty
        ? post.contentSource
        : post.content;
    final title = _showOriginal && post.titleSource.isNotEmpty
        ? post.titleSource
        : post.title;
    final titleDuplicate =
        title.trim().isNotEmpty &&
        (title.trim() == source.trim() ||
            source.trimLeft().startsWith(title.trim()));
    final truncated = source.length > 200 && !_expanded;
    final body = truncated ? '${source.substring(0, 200)}…' : source;
    final translated =
        post.contentSource.trim().isNotEmpty &&
        post.contentSource.trim() != post.content.trim();
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(VPushTokens.cardRadius),
        border: Border.all(color: theme.dividerColor),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              _PostAvatar(post: post),
              const SizedBox(width: 10),
              Expanded(
                child: Text(post.author, style: theme.textTheme.titleMedium),
              ),
              if (post.platform.isNotEmpty)
                Text(post.platform, style: theme.textTheme.bodyMedium),
            ],
          ),
          const SizedBox(height: 12),
          if (!titleDuplicate && title.trim().isNotEmpty)
            Text(title, style: theme.textTheme.titleMedium),
          if (translated)
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(
                onPressed: () => setState(() => _showOriginal = !_showOriginal),
                icon: const Icon(Icons.translate, size: 17),
                label: Text(_showOriginal ? '显示译文' : '显示原文'),
              ),
            ),
          Text(body.isEmpty ? '（无正文）' : body, style: theme.textTheme.bodyLarge),
          if (source.length > 200)
            Align(
              alignment: Alignment.centerLeft,
              child: TextButton.icon(
                onPressed: () => setState(() => _expanded = !_expanded),
                icon: Icon(
                  _expanded
                      ? Icons.keyboard_arrow_up
                      : Icons.keyboard_arrow_down,
                  size: 18,
                ),
                label: Text(_expanded ? '收起全文' : '展开全文'),
              ),
            ),
          if (post.images.isNotEmpty)
            _PostImages(images: post.images, author: post.author),
          if (post.files.isNotEmpty)
            _PostFiles(
              files: post.files,
              downloading: _downloading,
              onDownload: _downloadFile,
            ),
          if (post.tags.isNotEmpty)
            Wrap(
              spacing: 6,
              runSpacing: 4,
              children: post.tags
                  .map(
                    (tag) => Chip(
                      label: Text(tag),
                      visualDensity: VisualDensity.compact,
                    ),
                  )
                  .toList(),
            ),
          if (post.timestamp != null) ...[
            const SizedBox(height: 10),
            Text(post.timestamp!, style: theme.textTheme.bodyMedium),
          ],
          if (post.sourceUrl?.isNotEmpty == true && post.platform != 'zsxq')
            Align(
              alignment: Alignment.centerRight,
              child: TextButton.icon(
                onPressed: () => ExternalLinks.open(post.sourceUrl!),
                icon: const Icon(Icons.open_in_new, size: 17),
                label: const Text('查看原文'),
              ),
            ),
        ],
      ),
    );
  }

  Future<void> _downloadFile(TimelineFile file) async {
    if (_downloading) return;
    if (file.url.isNotEmpty) {
      await ExternalLinks.open(file.url);
      return;
    }
    if (file.id.isEmpty) return;
    setState(() => _downloading = true);
    try {
      final bytes = await widget.api.getBytes(
        '/media/zsxq-file/${Uri.encodeComponent(file.id)}',
      );
      final uri = await FileActions.cacheBytes(name: file.name, bytes: bytes);
      final opened = await FileActions.openCachedFile(
        uri,
        mimeType: _mimeType(file.name),
      );
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              opened ? '已交给系统打开 ${file.name}' : '没有可打开 ${file.name} 的应用',
            ),
          ),
        );
      }
    } on ApiException catch (exception) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text(exception.message)));
      }
    } finally {
      if (mounted) setState(() => _downloading = false);
    }
  }

  String _mimeType(String name) {
    final lower = name.toLowerCase();
    if (lower.endsWith('.pdf')) return 'application/pdf';
    if (lower.endsWith('.jpg') || lower.endsWith('.jpeg')) return 'image/jpeg';
    if (lower.endsWith('.png')) return 'image/png';
    if (lower.endsWith('.txt')) return 'text/plain';
    return 'application/octet-stream';
  }
}

class _PostAvatar extends StatelessWidget {
  const _PostAvatar({required this.post});

  final TimelinePost post;

  @override
  Widget build(BuildContext context) => CircleAvatar(
    radius: 18,
    backgroundImage: post.avatarUrl?.isNotEmpty == true
        ? NetworkImage(post.avatarUrl!)
        : null,
    child: post.avatarUrl?.isNotEmpty == true
        ? null
        : Text(post.author.isEmpty ? '?' : post.author.characters.first),
  );
}

class _PostImages extends StatelessWidget {
  const _PostImages({required this.images, required this.author});

  final List<String> images;
  final String author;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 12),
    child: Wrap(
      spacing: 6,
      runSpacing: 6,
      children: [
        for (var index = 0; index < images.length && index < 4; index++)
          GestureDetector(
            onTap: () => _openGallery(context, index),
            child: Hero(
              tag: '${author}_${index}_${images[index]}',
              child: Image.network(
                images[index],
                width: images.length == 1 ? double.infinity : 96,
                height: images.length == 1 ? 210 : 96,
                fit: BoxFit.cover,
                errorBuilder: (context, error, stack) => Container(
                  width: images.length == 1 ? double.infinity : 96,
                  height: images.length == 1 ? 210 : 96,
                  color: Theme.of(context).colorScheme.surfaceContainerHighest,
                  child: const Icon(Icons.broken_image_outlined),
                ),
              ),
            ),
          ),
        if (images.length > 4) Center(child: Text('+${images.length - 4}')),
      ],
    ),
  );

  Future<void> _openGallery(BuildContext context, int initial) =>
      showDialog<void>(
        context: context,
        barrierColor: Colors.black87,
        builder: (context) => Dialog.fullscreen(
          backgroundColor: Colors.black,
          child: Stack(
            children: [
              PageView.builder(
                controller: PageController(initialPage: initial),
                itemCount: images.length,
                itemBuilder: (context, index) => InteractiveViewer(
                  child: Center(
                    child: Image.network(
                      images[index],
                      fit: BoxFit.contain,
                      errorBuilder: (context, error, stack) => const Icon(
                        Icons.broken_image_outlined,
                        color: Colors.white,
                        size: 48,
                      ),
                    ),
                  ),
                ),
              ),
              SafeArea(
                child: Align(
                  alignment: Alignment.topRight,
                  child: IconButton(
                    tooltip: '关闭图片',
                    color: Colors.white,
                    onPressed: () => Navigator.pop(context),
                    icon: const Icon(Icons.close),
                  ),
                ),
              ),
            ],
          ),
        ),
      );
}

class _PostFiles extends StatelessWidget {
  const _PostFiles({
    required this.files,
    required this.downloading,
    required this.onDownload,
  });

  final List<TimelineFile> files;
  final bool downloading;
  final Future<void> Function(TimelineFile file) onDownload;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(top: 10),
    child: Wrap(
      spacing: 8,
      runSpacing: 6,
      children: files
          .map(
            (file) => OutlinedButton.icon(
              onPressed: downloading ? null : () => onDownload(file),
              icon: const Icon(Icons.attach_file, size: 17),
              label: Text(file.name),
            ),
          )
          .toList(),
    ),
  );
}

class MarketPanel extends StatelessWidget {
  const MarketPanel({super.key, required this.controller});

  final MarketController controller;

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: controller,
    builder: (context, child) {
      final theme = Theme.of(context);
      final quotes = controller.quotes;
      return Padding(
        padding: const EdgeInsets.fromLTRB(
          VPushTokens.pagePadding,
          8,
          VPushTokens.pagePadding,
          6,
        ),
        child: Card(
          elevation: 0,
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Text('市场概览', style: theme.textTheme.titleSmall),
                    const Spacer(),
                    Text(
                      controller.status.isEmpty
                          ? (controller.isLoading ? '加载中' : '')
                          : controller.status,
                    ),
                    IconButton(
                      tooltip: '刷新行情',
                      onPressed: controller.isLoading ? null : controller.load,
                      icon: const Icon(Icons.refresh, size: 18),
                    ),
                  ],
                ),
                SegmentedButton<String>(
                  segments: const [
                    ButtonSegment(value: 'day', label: Text('A 股 / 港股')),
                    ButtonSegment(value: 'night', label: Text('美股')),
                  ],
                  selected: {controller.group},
                  onSelectionChanged: (value) =>
                      controller.load(requestedGroup: value.first),
                ),
                if (controller.error != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text(
                      controller.error!,
                      style: TextStyle(color: theme.colorScheme.error),
                    ),
                  ),
                if (quotes.isNotEmpty)
                  ...quotes.take(6).map((quote) => _MarketRow(quote: quote)),
                if (!controller.isLoading &&
                    quotes.isEmpty &&
                    controller.error == null)
                  const Padding(
                    padding: EdgeInsets.all(8),
                    child: Text('暂无行情'),
                  ),
              ],
            ),
          ),
        ),
      );
    },
  );
}

class _MarketRow extends StatelessWidget {
  const _MarketRow({required this.quote});

  final MarketQuote quote;

  @override
  Widget build(BuildContext context) {
    final percent = quote.percent;
    final color = percent == null
        ? null
        : percent >= 0
        ? const Color(0xffb05b63)
        : const Color(0xff23714a);
    String display(double? value) =>
        value == null ? '--' : value.toStringAsFixed(2);
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Row(
        children: [
          Expanded(child: Text('${quote.name}  ${quote.symbol}')),
          Text(display(quote.price)),
          const SizedBox(width: 10),
          SizedBox(
            width: 64,
            child: Text(
              percent == null
                  ? '--'
                  : '${percent >= 0 ? '+' : ''}${display(percent)}%',
              textAlign: TextAlign.end,
              style: TextStyle(color: color),
            ),
          ),
        ],
      ),
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState();

  @override
  Widget build(BuildContext context) => Center(
    child: Text('暂无动态', style: Theme.of(context).textTheme.bodyMedium),
  );
}

class _ErrorState extends StatelessWidget {
  const _ErrorState({required this.message, required this.onRetry});

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) => Column(
    mainAxisAlignment: MainAxisAlignment.center,
    children: [
      Text(message, textAlign: TextAlign.center),
      const SizedBox(height: 12),
      OutlinedButton(onPressed: onRetry, child: const Text('重试')),
    ],
  );
}
