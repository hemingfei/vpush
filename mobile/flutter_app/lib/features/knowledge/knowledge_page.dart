import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:pdfrx/pdfrx.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api_client.dart';
import '../../core/theme/vpush_tokens.dart';
import 'knowledge_controller.dart';
import 'knowledge_models.dart';

class KnowledgePage extends StatefulWidget {
  const KnowledgePage({
    super.key,
    required this.api,
    this.mediaId,
    this.groupId = '',
  });

  final ApiClient api;
  final String? mediaId;
  final String groupId;

  @override
  State<KnowledgePage> createState() => _KnowledgePageState();
}

class _KnowledgePageState extends State<KnowledgePage> {
  late final KnowledgeController _controller = KnowledgeController(
    api: widget.api,
  );
  final _query = TextEditingController();
  Timer? _searchTimer;

  @override
  void initState() {
    super.initState();
    if (widget.mediaId == null) {
      _controller.load();
    } else {
      _controller.openDocument(widget.mediaId!, groupId: widget.groupId);
    }
  }

  @override
  void dispose() {
    _searchTimer?.cancel();
    _query.dispose();
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.mediaId != null) return _buildReader(context);
    return _buildList(context);
  }

  Widget _buildList(BuildContext context) => ListenableBuilder(
    listenable: _controller,
    builder: (context, child) {
      if (_controller.isLoading && _controller.documents.isEmpty) {
        return const Center(child: CircularProgressIndicator());
      }
      if (_controller.error != null && _controller.documents.isEmpty) {
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
            TextField(
              controller: _query,
              onChanged: _search,
              decoration: const InputDecoration(
                hintText: '搜索公司、代码或主题',
                prefixIcon: Icon(Icons.search),
              ),
            ),
            const SizedBox(height: 10),
            _GroupPicker(controller: _controller),
            if (_controller.days.isNotEmpty || _controller.tags.isNotEmpty) ...[
              const SizedBox(height: 8),
              _FacetRow(controller: _controller),
            ],
            const SizedBox(height: 14),
            if (_controller.documents.isEmpty)
              const Padding(
                padding: EdgeInsets.all(32),
                child: Center(child: Text('没有符合条件的研报')),
              )
            else
              ..._controller.documents.map(
                (doc) => _DocumentCard(document: doc),
              ),
            if (_controller.hasMore)
              Padding(
                padding: const EdgeInsets.all(16),
                child: OutlinedButton(
                  onPressed: () => _controller.loadDocuments(),
                  child: const Text('加载更多'),
                ),
              ),
          ],
        ),
      );
    },
  );

  Widget _buildReader(BuildContext context) => ListenableBuilder(
    listenable: _controller,
    builder: (context, child) {
      if (_controller.readerError != null && _controller.document == null) {
        return _ErrorState(
          message: _controller.readerError!,
          onRetry: () => _controller.openDocument(
            widget.mediaId!,
            groupId: widget.groupId,
          ),
        );
      }
      final document = _controller.document;
      if (document == null) {
        return const Center(child: CircularProgressIndicator());
      }
      final abstract = document.abstractZh.isNotEmpty
          ? document.abstractZh
          : document.abstractText;
      return ListView(
        padding: const EdgeInsets.fromLTRB(
          VPushTokens.pagePadding,
          14,
          VPushTokens.pagePadding,
          28,
        ),
        children: [
          Row(
            children: [
              IconButton(
                tooltip: '返回研报列表',
                onPressed: () => context.pop(),
                icon: const Icon(Icons.arrow_back),
              ),
              Expanded(
                child: Text(
                  document.name,
                  style: Theme.of(context).textTheme.headlineSmall,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            '${document.groupName} · ${document.day}',
            style: Theme.of(context).textTheme.bodyMedium,
          ),
          if (document.tags.isNotEmpty) ...[
            const SizedBox(height: 10),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: document.tags
                  .map((tag) => Chip(label: Text(tag)))
                  .toList(),
            ),
          ],
          if (abstract.isNotEmpty) ...[
            const SizedBox(height: 16),
            Text('摘要', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 6),
            Text(abstract),
          ],
          if (document.type == 'feishu_timeline')
            _FeishuTimeline(
              api: widget.api,
              mediaId: document.mediaId,
              groupId: document.groupId,
              entries: _controller.timelineEntries,
              notices: _controller.timelineNotices,
              loading: _controller.isLoadingTimeline,
            ),
          if (document.needsTranslation) ...[
            const SizedBox(height: 10),
            Align(
              alignment: Alignment.centerLeft,
              child: OutlinedButton.icon(
                onPressed: _controller.isTranslating
                    ? null
                    : _controller.translateDocument,
                icon: const Icon(Icons.translate),
                label: Text(_controller.isTranslating ? '翻译中' : '翻译摘要'),
              ),
            ),
          ],
          if (document.type == 'feishu_timeline' &&
              document.sourceUrl.isNotEmpty) ...[
            const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: () => launchUrl(Uri.parse(document.sourceUrl)),
              icon: const Icon(Icons.open_in_new),
              label: const Text('打开原文'),
            ),
          ],
          if (document.hasPdf) ...[
            const SizedBox(height: 18),
            FilledButton.icon(
              onPressed: _controller.isDownloadingPdf
                  ? null
                  : _controller.downloadPdf,
              icon: const Icon(Icons.picture_as_pdf_outlined),
              label: Text(_controller.isDownloadingPdf ? '加载 PDF…' : '打开 PDF'),
            ),
          ],
          if (document.hasTxt) ...[
            const SizedBox(height: 10),
            OutlinedButton.icon(
              onPressed: _controller.isLoadingText
                  ? null
                  : _controller.loadText,
              icon: const Icon(Icons.subject_outlined),
              label: Text(_controller.isLoadingText ? '加载全文…' : '打开全文'),
            ),
          ],
          if (_controller.textContent != null) ...[
            const SizedBox(height: 14),
            SelectableText(_controller.textContent!),
          ],
          if (_controller.readerError != null) ...[
            const SizedBox(height: 10),
            Text(
              _controller.readerError!,
              style: TextStyle(color: Theme.of(context).colorScheme.error),
            ),
          ],
          if (_controller.pdfBytes != null) ...[
            const SizedBox(height: 14),
            SizedBox(
              height: 620,
              child: PdfViewer.data(
                _controller.pdfBytes!,
                sourceName: document.mediaId,
              ),
            ),
          ],
        ],
      );
    },
  );

  void _search(String value) {
    _searchTimer?.cancel();
    _searchTimer = Timer(const Duration(milliseconds: 250), () async {
      _controller.setQuery(value);
      await _controller.loadDocuments(reset: true);
    });
  }
}

class _FeishuTimeline extends StatelessWidget {
  const _FeishuTimeline({
    required this.api,
    required this.mediaId,
    required this.groupId,
    required this.entries,
    required this.notices,
    required this.loading,
  });

  final ApiClient api;
  final String mediaId;
  final String groupId;
  final List<Map<String, dynamic>> entries;
  final List<Map<String, dynamic>> notices;
  final bool loading;

  @override
  Widget build(BuildContext context) {
    if (loading && entries.isEmpty) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 24),
        child: Center(child: CircularProgressIndicator()),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 18),
        Text('飞书时间线', style: Theme.of(context).textTheme.titleMedium),
        if (notices.isNotEmpty)
          ...notices.map(
            (notice) => Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(
                '${notice['text'] ?? notice['message'] ?? ''}',
                style: TextStyle(color: Theme.of(context).colorScheme.primary),
              ),
            ),
          ),
        if (entries.isEmpty)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 16),
            child: Text('暂无时间线记录'),
          )
        else
          ...entries.map(
            (entry) => _FeishuEntry(
              api: api,
              mediaId: mediaId,
              groupId: groupId,
              entry: entry,
            ),
          ),
      ],
    );
  }
}

class _FeishuEntry extends StatelessWidget {
  const _FeishuEntry({
    required this.api,
    required this.mediaId,
    required this.groupId,
    required this.entry,
  });

  final ApiClient api;
  final String mediaId;
  final String groupId;
  final Map<String, dynamic> entry;

  @override
  Widget build(BuildContext context) {
    final blocks = entry['blocks'];
    final blockList = blocks is List
        ? blocks.whereType<Map>().map(Map<String, dynamic>.from).toList()
        : const <Map<String, dynamic>>[];
    return Card(
      margin: const EdgeInsets.only(top: 10),
      elevation: 0,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '${entry['day'] ?? ''}  ${entry['time'] ?? entry['timestamp'] ?? ''}',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            ...blockList.map(
              (block) => _FeishuBlock(
                api: api,
                mediaId: mediaId,
                groupId: groupId,
                block: block,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _FeishuBlock extends StatelessWidget {
  const _FeishuBlock({
    required this.api,
    required this.mediaId,
    required this.groupId,
    required this.block,
  });

  final ApiClient api;
  final String mediaId;
  final String groupId;
  final Map<String, dynamic> block;

  @override
  Widget build(BuildContext context) {
    final rows = block['rows'];
    final assets = block['assets'];
    final text = '${block['text'] ?? ''}'.trim();
    final speaker = '${block['speaker'] ?? ''}'.trim();
    final assetList = assets is List
        ? assets.whereType<Map>().map(Map<String, dynamic>.from).toList()
        : const <Map<String, dynamic>>[];
    return Padding(
      padding: const EdgeInsets.only(top: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (speaker.isNotEmpty)
            Text(speaker, style: Theme.of(context).textTheme.labelLarge),
          if (text.isNotEmpty) SelectableText(text),
          if (rows is List)
            ...rows.whereType<List>().map(
              (row) => Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                  row
                      .map(
                        (cell) => '${cell is Map ? cell['text'] ?? '' : cell}',
                      )
                      .join('  '),
                ),
              ),
            ),
          if (assetList.isNotEmpty)
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: assetList
                  .map(
                    (asset) => _FeishuAsset(
                      api: api,
                      mediaId: mediaId,
                      groupId: groupId,
                      asset: asset,
                    ),
                  )
                  .toList(),
            ),
        ],
      ),
    );
  }
}

class _FeishuAsset extends StatefulWidget {
  const _FeishuAsset({
    required this.api,
    required this.mediaId,
    required this.groupId,
    required this.asset,
  });

  final ApiClient api;
  final String mediaId;
  final String groupId;
  final Map<String, dynamic> asset;

  @override
  State<_FeishuAsset> createState() => _FeishuAssetState();
}

class _FeishuAssetState extends State<_FeishuAsset> {
  Future<List<int>>? _future;

  @override
  void initState() {
    super.initState();
    final id = '${widget.asset['id'] ?? ''}';
    if (id.isNotEmpty) {
      _future = widget.api.getBytes(
        '/ima-documents/${Uri.encodeComponent(widget.mediaId)}/assets/${Uri.encodeComponent(id)}',
        query: widget.groupId.isEmpty ? null : {'group': widget.groupId},
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final name = '${widget.asset['name'] ?? '附件'}';
    final isImage =
        '${widget.asset['mime'] ?? ''}'.startsWith('image/') ||
        widget.asset['kind'] == 'image';
    if (!isImage || _future == null) {
      return OutlinedButton.icon(
        onPressed: _future == null ? null : _download,
        icon: const Icon(Icons.attach_file, size: 17),
        label: Text(name),
      );
    }
    return FutureBuilder<List<int>>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.hasError) return Text(name);
        if (!snapshot.hasData) {
          return const SizedBox(
            width: 96,
            height: 96,
            child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
          );
        }
        return Image.memory(
          Uint8List.fromList(snapshot.data!),
          width: 96,
          height: 96,
          fit: BoxFit.cover,
          errorBuilder: (context, error, stack) => Text(name),
        );
      },
    );
  }

  Future<void> _download() async {
    final future = _future;
    if (future == null) return;
    try {
      final bytes = await future;
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              '${widget.asset['name'] ?? '附件'} 已加载（${bytes.length} bytes）',
            ),
          ),
        );
      }
    } on Object catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(SnackBar(content: Text('$error')));
      }
    }
  }
}

class _GroupPicker extends StatelessWidget {
  const _GroupPicker({required this.controller});

  final KnowledgeController controller;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text('知识库', style: Theme.of(context).textTheme.titleSmall),
      const SizedBox(height: 6),
      Wrap(
        spacing: 6,
        runSpacing: 6,
        children: [
          FilterChip(
            label: const Text('全部'),
            selected: controller.group.isEmpty,
            onSelected: (_) => controller.setGroup(''),
          ),
          ...controller.subscribedGroups.map(
            (group) => FilterChip(
              label: Text(group.name),
              selected: controller.group == group.id,
              onSelected: (_) => controller.setGroup(group.id),
            ),
          ),
          ...controller.availableGroups.map(
            (group) => ActionChip(
              label: Text('订阅 ${group.name}'),
              onPressed: group.enabled
                  ? () => controller.toggleGroup(group)
                  : null,
            ),
          ),
        ],
      ),
    ],
  );
}

class _FacetRow extends StatelessWidget {
  const _FacetRow({required this.controller});

  final KnowledgeController controller;

  @override
  Widget build(BuildContext context) => Wrap(
    spacing: 6,
    runSpacing: 6,
    children: [
      if (controller.days.isNotEmpty)
        DropdownButton<String>(
          value: controller.day.isEmpty ? null : controller.day,
          hint: const Text('日期'),
          items: [
            const DropdownMenuItem(value: '', child: Text('全部日期')),
            ...controller.days.map(
              (day) => DropdownMenuItem(value: day, child: Text(day)),
            ),
          ],
          onChanged: (value) => controller.setDay(value ?? ''),
        ),
      ...controller.tags
          .take(12)
          .map(
            (value) => FilterChip(
              label: Text(value),
              selected: controller.tag == value,
              onSelected: (_) =>
                  controller.setTag(controller.tag == value ? '' : value),
            ),
          ),
    ],
  );
}

class _DocumentCard extends StatelessWidget {
  const _DocumentCard({required this.document});

  final KnowledgeDocument document;

  @override
  Widget build(BuildContext context) => Card(
    margin: const EdgeInsets.only(bottom: 10),
    elevation: 0,
    child: InkWell(
      onTap: () => context.push(
        '/knowledge/${Uri.encodeComponent(document.mediaId)}?group=${Uri.encodeQueryComponent(document.groupId)}',
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    document.name,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                Text(
                  document.day,
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
            if (document.abstractText.isNotEmpty) ...[
              const SizedBox(height: 6),
              Text(
                document.abstractText,
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
              ),
            ],
            const SizedBox(height: 8),
            Wrap(
              spacing: 6,
              children: [
                if (document.hasPdf) const Chip(label: Text('PDF')),
                if (document.hasTxt) const Chip(label: Text('全文')),
                ...document.tags.take(2).map((tag) => Chip(label: Text(tag))),
              ],
            ),
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
