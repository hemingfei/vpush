import 'package:url_launcher/url_launcher.dart';

class ExternalLinks {
  const ExternalLinks._();

  static Future<bool> open(String value) async {
    final uri = Uri.tryParse(value.trim());
    if (uri == null || (uri.scheme != 'http' && uri.scheme != 'https')) {
      return false;
    }
    return launchUrl(uri, mode: LaunchMode.externalApplication);
  }
}
