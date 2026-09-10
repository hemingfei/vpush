import 'package:flutter/material.dart';

import '../../core/api_client.dart';
import '../../core/session_store.dart';
import '../../core/theme/vpush_tokens.dart';
import 'settings_controller.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key, required this.api, required this.session});

  final ApiClient api;
  final SessionStore session;

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  late final SettingsController _controller = SettingsController(
    api: widget.api,
    session: widget.session,
  );
  final _telegram = TextEditingController();
  final _wecom = TextEditingController();
  final _bark = TextEditingController();
  final _keywords = TextEditingController();
  final _llmBase = TextEditingController();
  final _llmKey = TextEditingController();
  final _llmModel = TextEditingController();
  final _oldPassword = TextEditingController();
  final _newPassword = TextEditingController();
  final _confirmPassword = TextEditingController();
  int _tab = 0;
  bool _synced = false;

  @override
  void initState() {
    super.initState();
    _controller.addListener(_syncFields);
    _controller.load();
  }

  @override
  void dispose() {
    _controller
      ..removeListener(_syncFields)
      ..dispose();
    for (final field in [
      _telegram,
      _wecom,
      _bark,
      _keywords,
      _llmBase,
      _llmKey,
      _llmModel,
      _oldPassword,
      _newPassword,
      _confirmPassword,
    ]) {
      field.dispose();
    }
    super.dispose();
  }

  void _syncFields() {
    if (_synced || _controller.user.isEmpty) {
      if (_controller.user.isNotEmpty) _synced = true;
      return;
    }
    final user = _controller.user;
    _telegram.text = '${user['telegram_bot_token'] ?? ''}';
    _wecom.text = '${user['wecom_webhook'] ?? ''}';
    _bark.text = '${user['bark_key'] ?? ''}';
    final keywords = user['keywords'];
    _keywords.text = keywords is List ? keywords.join('\n') : '';
    _llmBase.text = '${user['llm_api_base'] ?? ''}';
    _llmKey.text = '${user['llm_api_key'] ?? ''}';
    _llmModel.text = '${user['llm_model'] ?? ''}';
    _synced = true;
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: _controller,
    builder: (context, child) {
      if (_controller.isLoading && _controller.user.isEmpty) {
        return const Center(child: CircularProgressIndicator());
      }
      if (_controller.error != null && _controller.user.isEmpty) {
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
          SegmentedButton<int>(
            segments: const [
              ButtonSegment(
                value: 0,
                label: Text('推送设置'),
                icon: Icon(Icons.notifications_outlined),
              ),
              ButtonSegment(
                value: 1,
                label: Text('渠道绑定'),
                icon: Icon(Icons.link),
              ),
              ButtonSegment(
                value: 2,
                label: Text('AI 网关'),
                icon: Icon(Icons.auto_awesome_outlined),
              ),
              ButtonSegment(
                value: 3,
                label: Text('账号'),
                icon: Icon(Icons.person_outline),
              ),
            ],
            selected: {_tab},
            onSelectionChanged: (value) => setState(() => _tab = value.first),
          ),
          const SizedBox(height: 16),
          if (_controller.error != null)
            _Message(text: _controller.error!, error: true),
          if (_controller.success != null) _Message(text: _controller.success!),
          switch (_tab) {
            0 => _buildPushTab(context),
            1 => _buildBindTab(context),
            2 => _buildLlmTab(context),
            _ => _buildAccountTab(context),
          },
        ],
      );
    },
  );

  Widget _buildPushTab(BuildContext context) {
    final user = _controller.user;
    return Column(
      children: [
        _Panel(
          title: '推送开关',
          child: Column(
            children: [
              SwitchListTile.adaptive(
                contentPadding: EdgeInsets.zero,
                title: const Text('新帖推送'),
                value: user['notify_enabled'] != false,
                onChanged: (value) => _save({'notify_enabled': value}),
              ),
              SwitchListTile.adaptive(
                contentPadding: EdgeInsets.zero,
                title: const Text('每日精选摘要'),
                value: user['daily_report_enabled'] == true,
                onChanged: (value) => _save({'daily_report_enabled': value}),
              ),
              SwitchListTile.adaptive(
                contentPadding: EdgeInsets.zero,
                title: const Text('X / Truth 翻译'),
                value: user['translate_twitter'] != false,
                onChanged: (value) => _save({'translate_twitter': value}),
              ),
            ],
          ),
        ),
        _Panel(
          title: '免打扰时段',
          child: Row(
            children: [
              Expanded(
                child: TextFormField(
                  initialValue: '${user['dnd_start'] ?? ''}',
                  decoration: const InputDecoration(labelText: '开始（HH:MM）'),
                  onChanged: (value) => user['dnd_start'] = value,
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: TextFormField(
                  initialValue: '${user['dnd_end'] ?? ''}',
                  decoration: const InputDecoration(labelText: '结束（HH:MM）'),
                  onChanged: (value) => user['dnd_end'] = value,
                ),
              ),
              IconButton(
                tooltip: '保存免打扰',
                onPressed: () => _save({
                  'dnd_start': user['dnd_start'] ?? '',
                  'dnd_end': user['dnd_end'] ?? '',
                  'dnd_allow_favorite': user['dnd_allow_favorite'] == true,
                }),
                icon: const Icon(Icons.save_outlined),
              ),
            ],
          ),
        ),
        _Panel(
          title: '关键词提醒',
          child: Column(
            children: [
              TextField(
                controller: _keywords,
                minLines: 4,
                maxLines: 8,
                decoration: const InputDecoration(hintText: '每行一个关键词，最多 20 个'),
              ),
              SwitchListTile.adaptive(
                contentPadding: EdgeInsets.zero,
                title: const Text('匹配研报中心'),
                value: user['keywords_match_reports'] == true,
                onChanged: (value) => _save({'keywords_match_reports': value}),
              ),
              Align(
                alignment: Alignment.centerRight,
                child: FilledButton.icon(
                  onPressed: () =>
                      _save({'keywords': _keywords.text.split('\n')}),
                  icon: const Icon(Icons.save_outlined),
                  label: const Text('保存关键词'),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildBindTab(BuildContext context) {
    final user = _controller.user;
    final selected = '${user['push_channels'] ?? ''}'
        .split(',')
        .where((item) => item.isNotEmpty)
        .toSet();
    return Column(
      children: [
        _Panel(
          title: '推送渠道',
          child: Column(
            children: [
              TextField(
                controller: _telegram,
                obscureText: true,
                decoration: const InputDecoration(
                  labelText: 'Telegram 自建机器人 token',
                ),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: _wecom,
                decoration: const InputDecoration(labelText: '企业微信 webhook'),
              ),
              const SizedBox(height: 10),
              TextField(
                controller: _bark,
                decoration: const InputDecoration(labelText: 'Bark key 或地址'),
              ),
              const SizedBox(height: 10),
              for (final channel in const [
                'telegram',
                'feishu',
                'wecom',
                'bark',
                'webpush',
              ])
                CheckboxListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(channel),
                  value: selected.contains(channel),
                  onChanged: (value) {
                    if (value == true) {
                      selected.add(channel);
                    } else {
                      selected.remove(channel);
                    }
                    _save({'push_channels': selected.join(',')});
                  },
                ),
              Align(
                alignment: Alignment.centerRight,
                child: FilledButton.icon(
                  onPressed: () => _save({
                    'telegram_bot_token': _telegram.text,
                    'wecom_webhook': _wecom.text,
                    'bark_key': _bark.text,
                    'push_channels': selected.join(','),
                  }),
                  icon: const Icon(Icons.save_outlined),
                  label: const Text('保存绑定'),
                ),
              ),
              const SizedBox(height: 8),
              Text('浏览器通知状态：${user['webpush_bound'] == true ? '已开启' : '未开启'}'),
            ],
          ),
        ),
        _Panel(
          title: '账号绑定码',
          child: Row(
            children: [
              Expanded(
                child: Text(
                  _controller.bindCode.isEmpty
                      ? '用于与机器人账号同步'
                      : '绑定码：${_controller.bindCode}',
                ),
              ),
              OutlinedButton.icon(
                onPressed: _controller.createBindCode,
                icon: const Icon(Icons.qr_code_2),
                label: const Text('生成'),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildLlmTab(BuildContext context) => _Panel(
    title: 'AI 网关',
    child: Column(
      children: [
        TextField(
          controller: _llmBase,
          decoration: const InputDecoration(labelText: 'API Base URL'),
        ),
        const SizedBox(height: 10),
        TextField(
          controller: _llmKey,
          obscureText: true,
          decoration: const InputDecoration(labelText: 'API Key'),
        ),
        const SizedBox(height: 10),
        TextField(
          controller: _llmModel,
          decoration: const InputDecoration(labelText: '模型'),
        ),
        const SizedBox(height: 12),
        Wrap(
          spacing: 8,
          children: [
            FilledButton.icon(
              onPressed: () => _save(_llmDraft()),
              icon: const Icon(Icons.save_outlined),
              label: const Text('保存'),
            ),
            OutlinedButton.icon(
              onPressed: () => _controller.loadModels(_llmDraft()),
              icon: const Icon(Icons.refresh),
              label: const Text('拉取模型'),
            ),
            OutlinedButton.icon(
              onPressed: () => _controller.testLlm(_llmDraft()),
              icon: const Icon(Icons.network_check),
              label: const Text('测试'),
            ),
          ],
        ),
        if (_controller.models.isNotEmpty) ...[
          const SizedBox(height: 12),
          DropdownButtonFormField<String>(
            initialValue: _controller.models.contains(_llmModel.text)
                ? _llmModel.text
                : null,
            decoration: const InputDecoration(labelText: '可用模型'),
            items: _controller.models
                .map(
                  (model) => DropdownMenuItem(value: model, child: Text(model)),
                )
                .toList(),
            onChanged: (value) {
              if (value != null) _llmModel.text = value;
            },
          ),
        ],
      ],
    ),
  );

  Widget _buildAccountTab(BuildContext context) => Column(
    children: [
      _Panel(
        title: '账号',
        child: Align(
          alignment: Alignment.centerLeft,
          child: Text('当前账号：${_controller.user['username'] ?? '未知'}'),
        ),
      ),
      _Panel(
        title: '修改密码',
        child: Column(
          children: [
            TextField(
              controller: _oldPassword,
              obscureText: true,
              decoration: const InputDecoration(labelText: '原密码'),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: _newPassword,
              obscureText: true,
              decoration: const InputDecoration(labelText: '新密码（至少 6 位）'),
            ),
            const SizedBox(height: 10),
            TextField(
              controller: _confirmPassword,
              obscureText: true,
              decoration: const InputDecoration(labelText: '确认新密码'),
            ),
            const SizedBox(height: 12),
            Align(
              alignment: Alignment.centerRight,
              child: FilledButton.icon(
                onPressed: _changePassword,
                icon: const Icon(Icons.lock_reset),
                label: const Text('修改密码'),
              ),
            ),
          ],
        ),
      ),
    ],
  );

  Map<String, dynamic> _llmDraft() => {
    'llm_api_base': _llmBase.text,
    'llm_api_key': _llmKey.text,
    'llm_model': _llmModel.text,
    'llm_api_format': 'chat',
  };

  Future<void> _save(Map<String, dynamic> updates) async {
    await _controller.save(updates);
    if (mounted) setState(() {});
  }

  Future<void> _changePassword() async {
    if (_newPassword.text != _confirmPassword.text) {
      setState(() => _controller.error = '两次输入的新密码不一致');
      return;
    }
    await _controller.changePassword(_oldPassword.text, _newPassword.text);
    if (mounted && _controller.success != null) {
      _oldPassword.clear();
      _newPassword.clear();
      _confirmPassword.clear();
    }
  }
}

class _Panel extends StatelessWidget {
  const _Panel({required this.title, required this.child});

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
            const SizedBox(height: 12),
            child,
          ],
        ),
      ),
    ),
  );
}

class _Message extends StatelessWidget {
  const _Message({required this.text, this.error = false});

  final String text;
  final bool error;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 12),
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
