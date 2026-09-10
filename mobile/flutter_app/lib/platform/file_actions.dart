import 'dart:io';

import 'package:path_provider/path_provider.dart';
import 'package:url_launcher/url_launcher.dart';

class FileActions {
  const FileActions._();

  static Future<Uri> cacheBytes({
    required String name,
    required List<int> bytes,
  }) async {
    final directory = await getTemporaryDirectory();
    final file = File('${directory.path}/${_safeName(name)}');
    await file.writeAsBytes(bytes, flush: true);
    return Uri.file(file.path);
  }

  static Future<bool> openCachedFile(Uri uri) =>
      launchUrl(uri, mode: LaunchMode.externalApplication);

  static String safeName(String value) => _safeName(value);

  static String _safeName(String value) {
    final trimmed = value.trim();
    final name = trimmed.isEmpty ? 'vpush-download' : trimmed;
    return name.replaceAll(RegExp(r'[^A-Za-z0-9._-]'), '_');
  }
}
