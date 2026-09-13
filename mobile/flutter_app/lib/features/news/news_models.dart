class NewsSource {
  const NewsSource({
    required this.id,
    required this.name,
    required this.selected,
    required this.enabled,
    this.status = '',
  });

  final int id;
  final String name;
  final bool selected;
  final bool enabled;
  final String status;

  factory NewsSource.fromJson(Map<String, dynamic> json) {
    final rawId = json['id'];
    return NewsSource(
      id: rawId is int ? rawId : int.tryParse('$rawId') ?? 0,
      name: '${json['name'] ?? json['slug'] ?? '未命名媒体'}',
      selected: json['selected'] == true,
      enabled: json['enabled'] != false,
      status: '${json['status'] ?? ''}',
    );
  }
}

class NewsItem {
  const NewsItem({
    required this.id,
    required this.title,
    required this.summary,
    required this.sourceName,
    required this.publishedAt,
    this.hasImage = false,
    this.isNew = false,
  });

  final int id;
  final String title;
  final String summary;
  final String sourceName;
  final String publishedAt;
  final bool hasImage;
  final bool isNew;

  factory NewsItem.fromJson(Map<String, dynamic> json) {
    final rawId = json['id'];
    return NewsItem(
      id: rawId is int ? rawId : int.tryParse('$rawId') ?? 0,
      title: '${json['title'] ?? '无标题'}',
      summary: '${json['summary'] ?? ''}',
      sourceName: '${json['source_name'] ?? ''}',
      publishedAt: '${json['published_at'] ?? ''}',
      hasImage: json['has_image'] == true,
      isNew: json['is_new'] == true,
    );
  }
}

class NewsArticle {
  const NewsArticle({
    required this.id,
    required this.title,
    required this.contentHtml,
    required this.sourceName,
    required this.publishedAt,
    required this.url,
    this.author,
    this.imageCount = 0,
  });

  final int id;
  final String title;
  final String contentHtml;
  final String sourceName;
  final String publishedAt;
  final String url;
  final String? author;
  final int imageCount;

  factory NewsArticle.fromJson(Map<String, dynamic> json) {
    final rawId = json['id'];
    final images = json['images'];
    return NewsArticle(
      id: rawId is int ? rawId : int.tryParse('$rawId') ?? 0,
      title: '${json['title'] ?? '无标题'}',
      contentHtml: '${json['content_html'] ?? '<p>暂无正文</p>'}',
      sourceName: '${json['source_name'] ?? ''}',
      publishedAt: '${json['published_at'] ?? ''}',
      url: '${json['url'] ?? ''}',
      author: json['author']?.toString(),
      imageCount: images is List ? images.length : 0,
    );
  }
}
