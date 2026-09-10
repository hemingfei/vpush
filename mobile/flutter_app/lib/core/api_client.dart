import 'package:dio/dio.dart';

import 'session_store.dart';

class ApiException implements Exception {
  ApiException(this.message, {this.statusCode, this.detail});

  final String message;
  final int? statusCode;
  final Object? detail;

  @override
  String toString() => message;
}

class ApiClient {
  ApiClient({required this.session, Dio? dio})
    : _dio =
          dio ??
          Dio(
            BaseOptions(
              baseUrl: const String.fromEnvironment(
                'API_BASE_URL',
                defaultValue: 'https://vpush.net',
              ),
              connectTimeout: const Duration(seconds: 12),
              receiveTimeout: const Duration(seconds: 30),
              headers: const {'Accept': 'application/json'},
            ),
          );

  final SessionStore session;
  final Dio _dio;

  Future<Map<String, dynamic>> getJson(
    String path, {
    Map<String, dynamic>? query,
    CancelToken? cancelToken,
  }) => _requestJson('GET', path, query: query, cancelToken: cancelToken);

  Future<List<dynamic>> getList(
    String path, {
    Map<String, dynamic>? query,
    CancelToken? cancelToken,
  }) async {
    final data = await _requestData(
      'GET',
      path,
      query: query,
      cancelToken: cancelToken,
    );
    if (data is List) return data;
    throw ApiException('服务端返回了无法识别的列表数据');
  }

  Future<Map<String, dynamic>> postJson(
    String path, {
    Map<String, dynamic>? body,
    Map<String, dynamic>? query,
    CancelToken? cancelToken,
  }) => _requestJson(
    'POST',
    path,
    body: body,
    query: query,
    cancelToken: cancelToken,
  );

  Future<Map<String, dynamic>> putJson(
    String path, {
    Map<String, dynamic>? body,
    Map<String, dynamic>? query,
    CancelToken? cancelToken,
  }) => _requestJson(
    'PUT',
    path,
    body: body,
    query: query,
    cancelToken: cancelToken,
  );

  Future<Map<String, dynamic>> patchJson(
    String path, {
    Map<String, dynamic>? body,
    Map<String, dynamic>? query,
    CancelToken? cancelToken,
  }) => _requestJson(
    'PATCH',
    path,
    body: body,
    query: query,
    cancelToken: cancelToken,
  );

  Future<Map<String, dynamic>> deleteJson(
    String path, {
    Map<String, dynamic>? query,
    CancelToken? cancelToken,
  }) => _requestJson('DELETE', path, query: query, cancelToken: cancelToken);

  Future<List<int>> getBytes(
    String path, {
    Map<String, dynamic>? query,
    CancelToken? cancelToken,
  }) async {
    final requestGeneration = session.generation;
    final token = session.token;
    try {
      final response = await _dio.get<List<int>>(
        _apiPath(path),
        queryParameters: query,
        cancelToken: cancelToken,
        options: Options(
          responseType: ResponseType.bytes,
          headers: token == null ? null : {'Authorization': 'Bearer $token'},
        ),
      );
      return response.data ?? const [];
    } on DioException catch (error) {
      if (error.response?.statusCode == 401 && !path.startsWith('/auth/')) {
        await session.clearIfGeneration(requestGeneration);
      }
      throw _toApiException(error);
    }
  }

  Future<String> getText(
    String path, {
    Map<String, dynamic>? query,
    CancelToken? cancelToken,
  }) async {
    final requestGeneration = session.generation;
    final token = session.token;
    try {
      final response = await _dio.get<String>(
        _apiPath(path),
        queryParameters: query,
        cancelToken: cancelToken,
        options: Options(
          responseType: ResponseType.plain,
          headers: token == null ? null : {'Authorization': 'Bearer $token'},
        ),
      );
      return response.data ?? '';
    } on DioException catch (error) {
      if (error.response?.statusCode == 401 && !path.startsWith('/auth/')) {
        await session.clearIfGeneration(requestGeneration);
      }
      throw _toApiException(error);
    }
  }

  Future<Map<String, dynamic>> _requestJson(
    String method,
    String path, {
    Map<String, dynamic>? body,
    Map<String, dynamic>? query,
    CancelToken? cancelToken,
  }) async {
    final data = await _requestData(
      method,
      path,
      body: body,
      query: query,
      cancelToken: cancelToken,
    );
    if (data is Map<String, dynamic>) return data;
    if (data is Map) return Map<String, dynamic>.from(data);
    throw ApiException('服务端返回了无法识别的对象数据');
  }

  Future<dynamic> _requestData(
    String method,
    String path, {
    Map<String, dynamic>? body,
    Map<String, dynamic>? query,
    CancelToken? cancelToken,
  }) async {
    final requestGeneration = session.generation;
    final token = session.token;
    try {
      final response = await _dio.request<dynamic>(
        _apiPath(path),
        data: body,
        queryParameters: query,
        cancelToken: cancelToken,
        options: Options(
          method: method,
          headers: token == null ? null : {'Authorization': 'Bearer $token'},
        ),
      );
      return response.data;
    } on DioException catch (error) {
      final statusCode = error.response?.statusCode;
      if (statusCode == 401 && !path.startsWith('/auth/')) {
        await session.clearIfGeneration(requestGeneration);
      }
      throw _toApiException(error);
    }
  }

  ApiException _toApiException(DioException error) {
    final statusCode = error.response?.statusCode;
    final data = error.response?.data;
    Object? detail;
    if (data is Map) detail = data['detail'];
    final message = switch (detail) {
      String value when value.isNotEmpty => value,
      List value when value.isNotEmpty =>
        value.map((item) => item.toString()).join('；'),
      _ when statusCode != null => '请求失败（$statusCode）',
      _ => error.type == DioExceptionType.cancel ? '请求已取消' : '网络连接失败，请稍后重试',
    };
    return ApiException(message, statusCode: statusCode, detail: detail);
  }

  String _apiPath(String path) {
    if (path == '/api' || path.startsWith('/api/')) return path;
    if (path.startsWith('/')) return '/api$path';
    return '/api/$path';
  }
}
