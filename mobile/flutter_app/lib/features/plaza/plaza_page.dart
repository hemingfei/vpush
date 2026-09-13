import 'dart:async';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_client.dart';
import '../../core/theme/vpush_tokens.dart';
import 'plaza_controller.dart';
import 'plaza_models.dart';

class PlazaPage extends StatefulWidget {
  const PlazaPage({super.key, required this.api, this.subscribedOnly = false});

  final ApiClient api;
  final bool subscribedOnly;

  @override
  State<PlazaPage> createState() => _PlazaPageState();
}

class _PlazaPageState extends State<PlazaPage> {
  late final PlazaController _controller = PlazaController(api: widget.api)
    ..subscribedOnly = widget.subscribedOnly;
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

  void _search(String value) {
    _searchTimer?.cancel();
    _searchTimer = Timer(const Duration(milliseconds: 200), () {
      _controller.setQuery(value);
    });
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: _controller,
      builder: (context, child) {
        if (_controller.isLoading && _controller.catalog.isEmpty) {
          return const Center(child: CircularProgressIndicator());
        }
        if (_controller.error != null && _controller.catalog.isEmpty) {
          return _ErrorState(
            message: _controller.error!,
            onRetry: _controller.load,
          );
        }
        final items = _controller.filtered;
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
              TextField(
                controller: _query,
                onChanged: _search,
                decoration: const InputDecoration(
                  hintText: '搜索昵称或 ID',
                  prefixIcon: Icon(Icons.search),
                ),
              ),
              const SizedBox(height: 10),
              _FilterRow(controller: _controller),
              const SizedBox(height: 12),
              Text(
                '共 ${_controller.catalog.length} 位大V · 已订阅 ${_controller.catalog.where((item) => item.subscribed).length} 位',
                style: Theme.of(context).textTheme.bodyMedium,
              ),
              const SizedBox(height: 10),
              if (items.isEmpty)
                const Padding(
                  padding: EdgeInsets.all(32),
                  child: Center(child: Text('没有匹配的大V')),
                )
              else
                ...items.map(
                  (kol) => _KolCard(controller: _controller, kol: kol),
                ),
            ],
          ),
        );
      },
    );
  }
}

class _FilterRow extends StatelessWidget {
  const _FilterRow({required this.controller});

  final PlazaController controller;

  @override
  Widget build(BuildContext context) => Wrap(
    spacing: 6,
    runSpacing: 6,
    children: [
      _Filter(
        label: '全部',
        selected: controller.platform.isEmpty,
        onTap: () => controller.setPlatform(''),
      ),
      _Filter(
        label: '雪球',
        selected: controller.platform == 'xueqiu',
        onTap: () => controller.setPlatform('xueqiu'),
      ),
      _Filter(
        label: '微博',
        selected: controller.platform == 'weibo',
        onTap: () => controller.setPlatform('weibo'),
      ),
      _Filter(
        label: 'X',
        selected: controller.platform == 'twitter',
        onTap: () => controller.setPlatform('twitter'),
      ),
      FilterChip(
        label: const Text('已订阅'),
        selected: controller.subscribedOnly,
        onSelected: (value) {
          controller.setSubscribedOnly(value);
        },
      ),
      FilterChip(
        label: const Text('特别关注'),
        selected: controller.favoriteOnly,
        onSelected: (value) {
          controller.setFavoriteOnly(value);
        },
      ),
    ],
  );
}

class _Filter extends StatelessWidget {
  const _Filter({
    required this.label,
    required this.selected,
    required this.onTap,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) => OutlinedButton(
    onPressed: onTap,
    style: OutlinedButton.styleFrom(
      minimumSize: const Size(0, 36),
      padding: const EdgeInsets.symmetric(horizontal: 12),
      backgroundColor: selected ? Theme.of(context).colorScheme.primary : null,
      foregroundColor: selected ? Colors.white : null,
      side: BorderSide(
        color: selected
            ? Theme.of(context).colorScheme.primary
            : Theme.of(context).dividerColor,
      ),
    ),
    child: Text(label),
  );
}

class _KolCard extends StatelessWidget {
  const _KolCard({required this.controller, required this.kol});

  final PlazaController controller;
  final PlazaKol kol;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(VPushTokens.radius),
        border: Border.all(color: theme.dividerColor),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          InkWell(
            onTap: () => context.push('/kol/${kol.id}'),
            child: Row(
              children: [
                CircleAvatar(
                  radius: 22,
                  backgroundImage: kol.avatarUrl == null
                      ? null
                      : NetworkImage(kol.avatarUrl!),
                  child: kol.avatarUrl == null
                      ? Text(kol.name.characters.first)
                      : null,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(kol.name, style: theme.textTheme.titleMedium),
                      const SizedBox(height: 3),
                      Text(
                        '${kol.platform} · ${kol.externalId}${kol.categoryName == null ? '' : ' · ${kol.categoryName}'}',
                        style: theme.textTheme.bodyMedium,
                      ),
                    ],
                  ),
                ),
                const Icon(Icons.chevron_right),
              ],
            ),
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: FilledButton.tonal(
                  onPressed: () => controller.toggleSubscription(kol),
                  child: Text(kol.subscribed ? '已订阅' : '订阅'),
                ),
              ),
              if (kol.subscribed) ...[
                IconButton(
                  tooltip: kol.favorite ? '取消特别关注' : '设为特别关注',
                  onPressed: () => controller.toggleFavorite(kol),
                  icon: Icon(kol.favorite ? Icons.star : Icons.star_border),
                  color: kol.favorite ? theme.colorScheme.primary : null,
                ),
                IconButton(
                  tooltip: kol.secondary ? '取消次要' : '设为次要',
                  onPressed: () => controller.toggleSecondary(kol),
                  icon: Icon(
                    kol.secondary
                        ? Icons.notifications_off
                        : Icons.notifications_none,
                  ),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }
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
