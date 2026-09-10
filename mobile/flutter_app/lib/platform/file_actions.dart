import 'dart:io';

import 'package:open_filex/open_filex.dart';
import 'package:path_provider/path_provider.dart';

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

  static Future<bool> openCachedFile(Uri uri, {String? mimeType}) async {
    final result = await OpenFilex.open(uri.toFilePath(), type: mimeType);
    return result.type == ResultType.done;
  }

  static String safeName(String value) => _safeName(value);

  static String _safeName(String value) {
    final trimmed = value.trim();
    final name = trimmed.isEmpty ? 'vpush-download' : trimmed;
    return name.replaceAll(RegExp(r'[^A-Za-z0-9._-]'), '_');
  }
}
