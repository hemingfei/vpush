class KnowledgeGroup {
  const KnowledgeGroup({
    required this.id,
    required this.name,
    required this.enabled,
    required this.subscribed,
    this.documentCount = 0,
    this.latestDay = '',
    this.latestTitle = '',
  });

  final String id;
  final String name;
  final bool enabled;
  final bool subscribed;
  final int documentCount;
  final String latestDay;
  final String latestTitle;

  factory KnowledgeGroup.fromJson(
    Map<String, dynamic> json, {
    required bool subscribed,
  }) {
    final rawCount = json['document_count'];
    return KnowledgeGroup(
      id: '${json['id'] ?? ''}',
      name: '${json['name'] ?? '未命名知识库'}',
      enabled: json['enabled'] != false,
      subscribed: subscribed,
      documentCount: rawCount is int
          ? rawCount
          : int.tryParse('$rawCount') ?? 0,
      latestDay: '${json['latest_day'] ?? ''}',
      latestTitle: '${json['latest_title'] ?? ''}',
    );
  }

  KnowledgeGroup copyWith({bool? subscribed}) => KnowledgeGroup(
    id: id,
    name: name,
    enabled: enabled,
    subscribed: subscribed ?? this.subscribed,
    documentCount: documentCount,
    latestDay: latestDay,
    latestTitle: latestTitle,
  );
}

class KnowledgeDocument {
  const KnowledgeDocument({
    required this.mediaId,
    required this.name,
    required this.day,
    required this.groupId,
    required this.groupName,
    required this.abstractText,
    required this.abstractZh,
    required this.needsTranslation,
    required this.tags,
    required this.hasPdf,
    required this.hasTxt,
    this.size = 0,
    this.chars = 0,
    this.coverUrl = '',
    this.type = 'document',
    this.sourceUrl = '',
  });

  final String mediaId;
  final String name;
  final String day;
  final String groupId;
  final String groupName;
  final String abstractText;
  final String abstractZh;
  final bool needsTranslation;
  final List<String> tags;
  final bool hasPdf;
  final bool hasTxt;
  final int size;
  final int chars;
  final String coverUrl;
  final String type;
  final String sourceUrl;

  factory KnowledgeDocument.fromJson(Map<String, dynamic> json) {
    final rawTags = json['tags'];
    final rawSize = json['size'];
    final rawChars = json['chars'];
    return KnowledgeDocument(
      mediaId: '${json['media_id'] ?? json['id'] ?? ''}',
      name: '${json['name'] ?? '未命名文档'}',
      day: '${json['day'] ?? json['sort_date'] ?? ''}',
      groupId: '${json['group_id'] ?? ''}',
      groupName: '${json['group_name'] ?? ''}',
      abstractText: '${json['abstract'] ?? ''}',
      abstractZh: '${json['abstract_zh'] ?? ''}',
      needsTranslation: json['needs_translation'] == true,
      tags: rawTags is List ? rawTags.map((tag) => '$tag').toList() : const [],
      hasPdf: json['has_pdf'] == true,
      hasTxt: json['has_txt'] == true,
      size: rawSize is int ? rawSize : int.tryParse('$rawSize') ?? 0,
      chars: rawChars is int ? rawChars : int.tryParse('$rawChars') ?? 0,
      coverUrl: '${json['cover_url'] ?? ''}',
      type: '${json['type'] ?? 'document'}',
      sourceUrl: '${json['source_url'] ?? ''}',
    );
  }
}
