import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_client.dart';
import '../../core/theme/vpush_tokens.dart';
import 'admin_controller.dart';

class AdminPage extends StatefulWidget {
  const AdminPage({super.key, required this.api, required this.section});

  final ApiClient api;
  final String section;

  @override
  State<AdminPage> createState() => _AdminPageState();
}

class _AdminPageState extends State<AdminPage> {
  late final AdminController _controller = AdminController(
    api: widget.api,
    section: widget.section,
  );
  final _count = TextEditingController(text: '1');
  final _note = TextEditingController();
  final _selectedKolIds = <int>{};

  @override
  void initState() {
    super.initState();
    if (widget.section != 'hub') _controller.load();
  }

  @override
  void dispose() {
    _controller.dispose();
    _count.dispose();
    _note.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.section == 'hub') {
      return _buildHub(context);
    }
    return ListenableBuilder(
      listenable: _controller,
      builder: (context, child) {
        if (_controller.isLoading && _controller.payload.isEmpty) {
          return const Center(child: CircularProgressIndicator());
        }
        if (_controller.error != null && _controller.payload.isEmpty) {
          return _ErrorState(
            message: _controller.error!,
            onRetry: _controller.load,
          );
        }
        return ListView(
          padding: const EdgeInsets.fromLTRB(
            VPushTokens.pagePadding,
            12,
            VPushTokens.pagePadding,
            32,
          ),
          children: [
            _AdminTabs(active: widget.section),
            const SizedBox(height: 14),
            if (_controller.error != null)
              _AdminMessage(text: _controller.error!, error: true),
            if (_controller.success != null)
              _AdminMessage(text: _controller.success!),
            _buildSection(context),
          ],
        );
      },
    );
  }

  Widget _buildHub(BuildContext context) => ListView(
    padding: const EdgeInsets.fromLTRB(
      VPushTokens.pagePadding,
      16,
      VPushTokens.pagePadding,
      32,
    ),
    children: [
      Text('管理', style: Theme.of(context).textTheme.headlineSmall),
      const SizedBox(height: 8),
      const Text('选择一个管理分区'),
      const SizedBox(height: 16),
      for (final item in _sections)
        Card(
          elevation: 0,
          child: ListTile(
            leading: Icon(item.icon),
            title: Text(item.label),
            subtitle: Text(item.description),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => context.push('/admin/${item.id}'),
          ),
        ),
    ],
  );

  Widget _buildSection(BuildContext context) => switch (widget.section) {
    'sources' => _SourcesSection(controller: _controller),
    'knowledge' => _KnowledgeSection(controller: _controller),
    'ops' => _OpsSection(controller: _controller),
    'accounts' => _AccountsSection(
      controller: _controller,
      count: _count,
      note: _note,
    ),
    _ => _ContentSection(
      controller: _controller,
      selectedIds: _selectedKolIds,
      onSelectionChanged: () => setState(() {}),
    ),
  };
}

class _AdminTabs extends StatelessWidget {
  const _AdminTabs({required this.active});

  final String active;

  @override
  Widget build(BuildContext context) => SingleChildScrollView(
    scrollDirection: Axis.horizontal,
    child: Row(
      children: [
        for (final item in _sections)
          Padding(
            padding: const EdgeInsets.only(right: 8),
            child: ChoiceChip(
              label: Text(item.label),
              selected: active == item.id,
              onSelected: (_) => context.go('/admin/${item.id}'),
            ),
          ),
      ],
    ),
  );
}

class _ContentSection extends StatelessWidget {
  const _ContentSection({
    required this.controller,
    required this.selectedIds,
    required this.onSelectionChanged,
  });

  final AdminController controller;
  final Set<int> selectedIds;
  final VoidCallback onSelectionChanged;

  @override
  Widget build(BuildContext context) {
    final kols = (controller.payload['/admin/kols'] as Map?)?['items'];
    final requests = controller.payload['/admin/kol-requests'];
    return Column(
      children: [
        _AdminPanel(
          title: '大 V 目录',
          child: kols is List && kols.isNotEmpty
              ? Column(
                  children: [
                    for (final raw in kols.whereType<Map>())
                      CheckboxListTile(
                        contentPadding: EdgeInsets.zero,
                        value: selectedIds.contains(_id(raw['id'])),
                        title: Text('${raw['name'] ?? '未命名'}'),
                        subtitle: Text(
                          '${raw['platform'] ?? ''} · ${raw['external_id'] ?? ''}',
                        ),
                        onChanged: (value) {
                          final id = _id(raw['id']);
                          if (value == true) {
                            selectedIds.add(id);
                          } else {
                            selectedIds.remove(id);
                          }
                          onSelectionChanged();
                        },
                      ),
                    Align(
                      alignment: Alignment.centerRight,
                      child: Wrap(
                        spacing: 8,
                        children: [
                          OutlinedButton.icon(
                            onPressed: selectedIds.isEmpty
                                ? null
                                : () => controller.batchKols(
                                    ids: selectedIds.toList(),
                                    action: 'enable',
                                  ),
                            icon: const Icon(Icons.visibility_outlined),
                            label: const Text('启用'),
                          ),
                          OutlinedButton.icon(
                            onPressed: selectedIds.isEmpty
                                ? null
                                : () => controller.batchKols(
                                    ids: selectedIds.toList(),
                                    action: 'disable',
                                  ),
                            icon: const Icon(Icons.visibility_off_outlined),
                            label: const Text('停用'),
                          ),
                        ],
                      ),
                    ),
                  ],
                )
              : const Text('暂无目录数据'),
        ),
        _AdminPanel(
          title: '添加申请',
          child: requests is List && requests.isNotEmpty
              ? Column(
                  children: [
                    for (final raw in requests.whereType<Map>())
                      ListTile(
                        contentPadding: EdgeInsets.zero,
                        title: Text(
                          '${raw['name'] ?? raw['external_id'] ?? '申请'}',
                        ),
                        subtitle: Text(
                          '${raw['platform'] ?? ''} · ${raw['status'] ?? 'pending'}',
                        ),
                        trailing: Wrap(
                          children: [
                            IconButton(
                              tooltip: '通过',
                              icon: const Icon(Icons.check),
                              onPressed: _id(raw['id']) == 0
                                  ? null
                                  : () => controller.approveRequest(
                                      _id(raw['id']),
                                      approve: true,
                                    ),
                            ),
                            IconButton(
                              tooltip: '拒绝',
                              icon: const Icon(Icons.close),
                              onPressed: _id(raw['id']) == 0
                                  ? null
                                  : () => controller.approveRequest(
                                      _id(raw['id']),
                                      approve: false,
                                    ),
                            ),
                          ],
                        ),
                      ),
                  ],
                )
              : const Text('暂无添加申请'),
        ),
      ],
    );
  }
}

class _SourcesSection extends StatelessWidget {
  const _SourcesSection({required this.controller});

  final AdminController controller;

  @override
  Widget build(BuildContext context) {
    final settings = controller.payload['/admin/news/settings'];
    final sources =
        (controller.payload['/admin/news/sources'] as Map?)?['items'];
    return Column(
      children: [
        _AdminPanel(
          title: '新闻采集',
          child: settings is Map
              ? SwitchListTile.adaptive(
                  contentPadding: EdgeInsets.zero,
                  title: const Text('启用财经新闻'),
                  value: settings['enabled'] == true,
                  onChanged: (value) =>
                      controller.saveNewsSettings({'enabled': value}),
                )
              : const Text('暂无新闻设置'),
        ),
        _AdminPanel(
          title: '新闻来源',
          child: sources is List && sources.isNotEmpty
              ? Column(
                  children: [
                    for (final source in sources.whereType<Map>())
                      ListTile(
                        contentPadding: EdgeInsets.zero,
                        title: Text('${source['name'] ?? ''}'),
                        subtitle: Text(
                          source['enabled'] == true ? '已启用' : '已停用',
                        ),
                      ),
                  ],
                )
              : const Text('暂无来源'),
        ),
        _AdminPanel(
          title: '广场数据源',
          child: Text(
            '${controller.payload['/admin/plaza-sources'] ?? '暂无数据'}',
          ),
        ),
      ],
    );
  }
}

class _KnowledgeSection extends StatelessWidget {
  const _KnowledgeSection({required this.controller});

  final AdminController controller;

  @override
  Widget build(BuildContext context) => Column(
    children: [
      _AdminPanel(
        title: '研报采集状态',
        child: _ValueList(controller.payload['/admin/ima-collector']),
      ),
      _AdminPanel(
        title: '存储健康',
        child: _ValueList(controller.payload['/admin/ima-storage/health']),
      ),
    ],
  );
}

class _OpsSection extends StatelessWidget {
  const _OpsSection({required this.controller});

  final AdminController controller;

  @override
  Widget build(BuildContext context) {
    final logs = controller.payload['/admin/logs'];
    return Column(
      children: [
        _AdminPanel(
          title: '运行看板',
          child: _ValueList(controller.payload['/admin/dashboard']),
        ),
        _AdminPanel(
          title: '审计日志',
          child: logs is List && logs.isNotEmpty
              ? Column(
                  children: [
                    for (final log in logs.take(30))
                      ListTile(
                        contentPadding: EdgeInsets.zero,
                        title: Text(
                          '${log is Map ? log['action'] ?? '' : log}',
                        ),
                        subtitle: Text(
                          '${log is Map ? log['created_at'] ?? '' : ''}',
                        ),
                      ),
                  ],
                )
              : const Text('暂无日志'),
        ),
      ],
    );
  }
}

class _AccountsSection extends StatelessWidget {
  const _AccountsSection({
    required this.controller,
    required this.count,
    required this.note,
  });

  final AdminController controller;
  final TextEditingController count;
  final TextEditingController note;

  @override
  Widget build(BuildContext context) {
    final codes = controller.payload['/admin/register-codes'];
    return Column(
      children: [
        _AdminPanel(
          title: '生成注册码',
          child: Row(
            children: [
              SizedBox(
                width: 80,
                child: TextField(
                  controller: count,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(labelText: '数量'),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: TextField(
                  controller: note,
                  decoration: const InputDecoration(labelText: '备注'),
                ),
              ),
              IconButton(
                tooltip: '生成',
                onPressed: () => controller.generateCodes(
                  count: int.tryParse(count.text) ?? 1,
                  note: note.text,
                ),
                icon: const Icon(Icons.add_circle_outline),
              ),
            ],
          ),
        ),
        _AdminPanel(
          title: '注册码列表',
          child: codes is List && codes.isNotEmpty
              ? Column(
                  children: [
                    for (final code in codes.take(100))
                      ListTile(
                        contentPadding: EdgeInsets.zero,
                        title: Text(
                          '${code is Map ? code['code'] ?? '' : code}',
                        ),
                        subtitle: Text(
                          '${code is Map ? code['used_at'] ?? '未使用' : ''}',
                        ),
                      ),
                  ],
                )
              : const Text('暂无注册码'),
        ),
      ],
    );
  }
}

class _AdminPanel extends StatelessWidget {
  const _AdminPanel({required this.title, required this.child});

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
            const SizedBox(height: 10),
            child,
          ],
        ),
      ),
    ),
  );
}

class _AdminMessage extends StatelessWidget {
  const _AdminMessage({required this.text, this.error = false});

  final String text;
  final bool error;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 10),
    child: Text(
      text,
      style: TextStyle(
        color: error
            ? Theme.of(context).colorScheme.error
            : Theme.of(context).colorScheme.primary,
      ),
    ),
  );
}

class _ValueList extends StatelessWidget {
  const _ValueList(this.value);

  final Object? value;

  @override
  Widget build(BuildContext context) {
    if (value is Map && (value as Map).isNotEmpty) {
      return Column(
        children: [
          ...(value as Map).entries
              .take(20)
              .map(
                (entry) => ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text('${entry.key}'),
                  trailing: Text('${entry.value}'),
                ),
              ),
        ],
      );
    }
    return Text(value?.toString() ?? '暂无数据');
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

int _id(Object? value) => value is int ? value : int.tryParse('$value') ?? 0;

class _AdminSection {
  const _AdminSection(this.id, this.label, this.description, this.icon);

  final String id;
  final String label;
  final String description;
  final IconData icon;
}

const _sections = [
  _AdminSection('content', '内容管理', '大 V 目录和添加申请', Icons.library_books_outlined),
  _AdminSection('sources', '数据源', '新闻与平台采集设置', Icons.source_outlined),
  _AdminSection('knowledge', '研报设置', '知识库采集与存储状态', Icons.menu_book_outlined),
  _AdminSection('ops', '帖子与日志', '看板和审计记录', Icons.monitor_heart_outlined),
  _AdminSection(
    'accounts',
    '用户与注册',
    '注册码与账号操作',
    Icons.manage_accounts_outlined,
  ),
];
