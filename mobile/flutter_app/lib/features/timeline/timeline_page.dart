import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/theme/vpush_tokens.dart';
import 'timeline_controller.dart';
import 'timeline_models.dart';

class TimelinePage extends StatefulWidget {
  const TimelinePage({super.key, required this.api});

  final ApiClient api;

  @override
  State<TimelinePage> createState() => _TimelinePageState();
}

class _TimelinePageState extends State<TimelinePage> {
  late final TimelineController _controller = TimelineController(
    api: widget.api,
  );
  final _query = TextEditingController();

  @override
  void initState() {
    super.initState();
    _controller.load();
  }

  @override
  void dispose() {
    _controller.dispose();
    _query.dispose();
    super.dispose();
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
                        _controller.load(reset: false);
                        return const Padding(
                          padding: EdgeInsets.all(16),
                          child: Center(
                            child: CircularProgressIndicator(strokeWidth: 2),
                          ),
                        );
                      }
                      return _PostCard(post: _controller.posts[index]);
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

class _PostCard extends StatelessWidget {
  const _PostCard({required this.post});

  final TimelinePost post;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
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
              CircleAvatar(
                radius: 18,
                backgroundImage: post.avatarUrl == null
                    ? null
                    : NetworkImage(post.avatarUrl!),
                child: post.avatarUrl == null
                    ? Text(post.author.characters.first)
                    : null,
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(post.author, style: theme.textTheme.titleMedium),
              ),
              if (post.platform.isNotEmpty)
                Text(post.platform, style: theme.textTheme.bodyMedium),
            ],
          ),
          const SizedBox(height: 12),
          Text(post.content, style: theme.textTheme.bodyLarge),
          if (post.timestamp != null) ...[
            const SizedBox(height: 10),
            Text(post.timestamp!, style: theme.textTheme.bodyMedium),
          ],
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
