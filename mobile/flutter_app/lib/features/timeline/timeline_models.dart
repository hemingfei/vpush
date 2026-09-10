import 'dart:convert';

class TimelinePost {
  const TimelinePost({
    required this.id,
    required this.author,
    required this.platform,
    required this.content,
    this.timestamp,
    this.avatarUrl,
    this.sourceUrl,
    this.favorite = false,
    this.kolId,
    this.title = '',
    this.titleSource = '',
    this.contentSource = '',
    this.postType = '',
    this.images = const [],
    this.files = const [],
    this.tags = const [],
    this.detail,
  });

  final int id;
  final String author;
  final String platform;
  final String content;
  final String? timestamp;
  final String? avatarUrl;
  final String? sourceUrl;
  final bool favorite;
  final int? kolId;
  final String title;
  final String titleSource;
  final String contentSource;
  final String postType;
  final List<String> images;
  final List<TimelineFile> files;
  final List<String> tags;
  final Map<String, dynamic>? detail;

  factory TimelinePost.fromJson(Map<String, dynamic> json) {
    final rawId = json['id'];
    final id = rawId is int ? rawId : int.tryParse('$rawId') ?? 0;
    final content =
        json['content'] ?? json['text'] ?? json['description'] ?? '';
    final rawImages = json['images'];
    final rawTags = json['tags'];
    final rawDetail = json['detail'];
    Map<String, dynamic>? detail;
    if (rawDetail is Map) {
      detail = Map<String, dynamic>.from(rawDetail);
    } else if (rawDetail is String && rawDetail.isNotEmpty) {
      try {
        final decoded = jsonDecode(rawDetail);
        if (decoded is Map) detail = Map<String, dynamic>.from(decoded);
      } on FormatException {
        detail = null;
      }
    }
    final detailFiles = detail?['files'];
    final files = <TimelineFile>[];
    if (detailFiles is List) {
      files.addAll(
        detailFiles.whereType<Map>().map(
          (file) => TimelineFile.fromJson(Map<String, dynamic>.from(file)),
        ),
      );
    }
    final rawKolId = json['kol_id'];
    return TimelinePost(
      id: id,
      author: '${json['kol_name'] ?? json['author'] ?? json['name'] ?? '未知来源'}',
      platform: '${json['platform'] ?? ''}',
      content: '$content',
      timestamp:
          json['timestamp']?.toString() ?? json['created_at']?.toString(),
      avatarUrl: json['avatar_url']?.toString(),
      sourceUrl: json['source_url']?.toString() ?? json['url']?.toString(),
      favorite: json['favorite'] == true,
      kolId: rawKolId is int ? rawKolId : int.tryParse('$rawKolId'),
      title: '${json['title'] ?? ''}',
      titleSource: '${json['title_src'] ?? ''}',
      contentSource: '${json['content_src'] ?? ''}',
      postType: '${json['post_type'] ?? ''}',
      images: rawImages is List
          ? rawImages
                .map((image) => '$image')
                .where((image) => image.isNotEmpty)
                .toList()
          : const [],
      files: files,
      tags: rawTags is List
          ? rawTags.map((tag) => '$tag').where((tag) => tag.isNotEmpty).toList()
          : const [],
      detail: detail,
    );
  }
}

class TimelineFile {
  const TimelineFile({this.id = '', this.name = '附件', this.url = ''});

  final String id;
  final String name;
  final String url;

  factory TimelineFile.fromJson(Map<String, dynamic> json) => TimelineFile(
    id: '${json['file_id'] ?? json['id'] ?? ''}',
    name: '${json['name'] ?? json['filename'] ?? '附件'}',
    url: '${json['url'] ?? ''}',
  );
}

class MarketQuote {
  const MarketQuote({
    required this.symbol,
    required this.name,
    required this.price,
    required this.change,
    required this.percent,
    this.status = '',
    this.quotedAt = '',
  });

  final String symbol;
  final String name;
  final double? price;
  final double? change;
  final double? percent;
  final String status;
  final String quotedAt;

  factory MarketQuote.fromJson(Map<String, dynamic> json) {
    double? number(Object? value) =>
        value is num ? value.toDouble() : double.tryParse('$value');
    return MarketQuote(
      symbol: '${json['symbol'] ?? ''}',
      name: '${json['name'] ?? json['symbol'] ?? ''}',
      price: number(json['price']),
      change: number(json['change']),
      percent: number(json['percent']),
      status: '${json['status'] ?? ''}',
      quotedAt: '${json['quoted_at'] ?? ''}',
    );
  }
}
