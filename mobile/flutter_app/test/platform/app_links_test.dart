import 'package:flutter_test/flutter_test.dart';

import 'package:vpush/platform/app_links.dart';

void main() {
  test('resolves supported https and custom-scheme links to app routes', () {
    expect(
      AppLinkResolver.resolve(Uri.parse('https://vpush.net/news/42')),
      '/news/42',
    );
    expect(AppLinkResolver.resolve(Uri.parse('vpush://news/42')), '/news/42');
    expect(
      AppLinkResolver.resolve(Uri.parse('https://vpush.net/home?subscribed=1')),
      '/home?subscribed=1',
    );
    expect(AppLinkResolver.resolveRoute('/news/42'), '/news/42');
    expect(
      AppLinkResolver.resolve(Uri.parse('vpush://knowledge/doc-1?group=ima')),
      '/knowledge/doc-1?group=ima',
    );
  });

  test('rejects untrusted hosts, malformed ids, and unsupported queries', () {
    expect(
      AppLinkResolver.resolve(Uri.parse('https://evil.example/news/42')),
      isNull,
    );
    expect(
      AppLinkResolver.resolve(Uri.parse('https://vpush.net/news/not-an-id')),
      isNull,
    );
    expect(
      AppLinkResolver.resolve(
        Uri.parse('https://vpush.net/home?next=https://evil.example'),
      ),
      isNull,
    );
  });
}
