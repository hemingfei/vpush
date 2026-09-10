import 'package:flutter_test/flutter_test.dart';

import 'package:vpush/platform/external_links.dart';
import 'package:vpush/platform/file_actions.dart';

void main() {
  test('sanitizes cache names without path traversal', () {
    expect(FileActions.safeName('../secret.pdf'), '.._secret.pdf');
    expect(FileActions.safeName(''), 'vpush-download');
  });

  test('rejects non-http external links', () async {
    expect(await ExternalLinks.open('javascript:alert(1)'), isFalse);
    expect(await ExternalLinks.open('/internal/path'), isFalse);
  });
}
