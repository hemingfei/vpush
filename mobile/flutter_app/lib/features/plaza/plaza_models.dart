class PlazaKol {
  const PlazaKol({
    required this.id,
    required this.name,
    required this.platform,
    required this.externalId,
    this.avatarUrl,
    this.categoryName,
    this.subscribed = false,
    this.subscribeType = 'post',
    this.favorite = false,
    this.secondary = false,
  });

  final int id;
  final String name;
  final String platform;
  final String externalId;
  final String? avatarUrl;
  final String? categoryName;
  final bool subscribed;
  final String subscribeType;
  final bool favorite;
  final bool secondary;

  PlazaKol copyWith({
    bool? subscribed,
    String? subscribeType,
    bool? favorite,
    bool? secondary,
  }) => PlazaKol(
    id: id,
    name: name,
    platform: platform,
    externalId: externalId,
    avatarUrl: avatarUrl,
    categoryName: categoryName,
    subscribed: subscribed ?? this.subscribed,
    subscribeType: subscribeType ?? this.subscribeType,
    favorite: favorite ?? this.favorite,
    secondary: secondary ?? this.secondary,
  );

  factory PlazaKol.fromJson(Map<String, dynamic> json) {
    final rawId = json['id'];
    return PlazaKol(
      id: rawId is int ? rawId : int.tryParse('$rawId') ?? 0,
      name: '${json['name'] ?? '未命名大V'}',
      platform: '${json['platform'] ?? ''}',
      externalId: '${json['external_id'] ?? ''}',
      avatarUrl: json['avatar_url']?.toString(),
      categoryName: json['category_name']?.toString(),
      subscribed: json['subscribed'] == true,
      subscribeType: '${json['subscribe_type'] ?? 'post'}',
      favorite: json['favorite'] == true,
      secondary: json['secondary'] == true,
    );
  }
}
