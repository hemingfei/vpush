import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_client.dart';
import '../../core/theme/vpush_tokens.dart';
import 'plaza_models.dart';

class KolDetailPage extends StatefulWidget {
  const KolDetailPage({super.key, required this.api, required this.kolId});

  final ApiClient api;
  final int kolId;

  @override
  State<KolDetailPage> createState() => _KolDetailPageState();
}

class _KolDetailPageState extends State<KolDetailPage> {
  PlazaKol? _kol;
  List<Map<String, dynamic>> _posts = [];
  Map<String, dynamic>? _holdings;
  Map<String, dynamic>? _nav;
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final kol = await widget.api.getJson('/kols/${widget.kolId}');
      final posts = await widget.api.getList('/kols/${widget.kolId}/posts');
      Map<String, dynamic>? holdings;
      Map<String, dynamic>? nav;
      if ('${kol['platform'] ?? ''}' == 'combination') {
        try {
          holdings = await widget.api.getJson('/kols/${widget.kolId}/holdings');
          nav = await widget.api.getJson('/kols/${widget.kolId}/nav');
        } on ApiException {
          // Quote data is optional for a combination; keep its profile usable.
        }
      }
      if (!mounted) return;
      setState(() {
        _kol = PlazaKol.fromJson(kol);
        _posts = posts.whereType<Map>().map(Map<String, dynamic>.from).toList();
        _holdings = holdings;
        _nav = nav;
        _loading = false;
      });
    } on ApiException catch (exception) {
      if (mounted) {
        setState(() {
          _error = exception.message;
          _loading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_error != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Text(_error!),
            const SizedBox(height: 12),
            OutlinedButton(onPressed: _load, child: const Text('重试')),
          ],
        ),
      );
    }
    final kol = _kol;
    if (kol == null) return const Center(child: Text('大 V 不存在'));
    return ListView(
      padding: const EdgeInsets.fromLTRB(
        VPushTokens.pagePadding,
        12,
        VPushTokens.pagePadding,
        28,
      ),
      children: [
        Row(
          children: [
            IconButton(
              tooltip: '返回广场',
              onPressed: () => context.pop(),
              icon: const Icon(Icons.arrow_back),
            ),
            Expanded(
              child: Text(
                kol.name,
                style: Theme.of(context).textTheme.headlineSmall,
              ),
            ),
          ],
        ),
        Text(
          '${kol.platform} · ${kol.externalId}',
          style: Theme.of(context).textTheme.bodyMedium,
        ),
        if (kol.categoryName != null)
          Text(
            kol.categoryName!,
            style: Theme.of(context).textTheme.bodyMedium,
          ),
        const SizedBox(height: 14),
        _DetailPanel(
          title: '资料',
          child: Text(kol.subscribed ? '当前账号已订阅' : '当前账号未订阅'),
        ),
        if (_holdings != null)
          _DetailPanel(title: '当前持仓', child: _MapSummary(_holdings!)),
        if (_nav != null) _DetailPanel(title: '净值', child: _MapSummary(_nav!)),
        _DetailPanel(
          title: '历史动态（${_posts.length}）',
          child: _posts.isEmpty
              ? const Text('暂无动态')
              : Column(
                  children: [
                    for (final post in _posts.take(30))
                      ListTile(
                        contentPadding: EdgeInsets.zero,
                        title: Text('${post['content'] ?? ''}'),
                        subtitle: Text('${post['published_at'] ?? ''}'),
                      ),
                  ],
                ),
        ),
      ],
    );
  }
}

class _DetailPanel extends StatelessWidget {
  const _DetailPanel({required this.title, required this.child});

  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 12),
    child: Card(
      elevation: 0,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            child,
          ],
        ),
      ),
    ),
  );
}

class _MapSummary extends StatelessWidget {
  const _MapSummary(this.data);

  final Map<String, dynamic> data;

  @override
  Widget build(BuildContext context) => Column(
    children: [
      for (final entry in data.entries.take(12))
        ListTile(
          contentPadding: EdgeInsets.zero,
          title: Text(entry.key),
          trailing: Text('${entry.value}'),
        ),
    ],
  );
}
