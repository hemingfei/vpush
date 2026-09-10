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
  });

  final int id;
  final String author;
  final String platform;
  final String content;
  final String? timestamp;
  final String? avatarUrl;
  final String? sourceUrl;
  final bool favorite;

  factory TimelinePost.fromJson(Map<String, dynamic> json) {
    final rawId = json['id'];
    final id = rawId is int ? rawId : int.tryParse('$rawId') ?? 0;
    final content =
        json['content'] ?? json['text'] ?? json['description'] ?? '';
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
    );
  }
}
