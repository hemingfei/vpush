import 'package:flutter/services.dart';

import '../core/api_client.dart';

class AndroidPushDevice {
  const AndroidPushDevice({
    required this.installationId,
    required this.provider,
    required this.token,
    this.deviceModel = '',
    this.appVersion = '',
  });

  final String installationId;
  final String provider;
  final String token;
  final String deviceModel;
  final String appVersion;
}

abstract interface class AndroidPushPlatform {
  Future<AndroidPushDevice?> getDevice();
  Future<bool> requestPermission();
}

class MethodChannelAndroidPushPlatform implements AndroidPushPlatform {
  MethodChannelAndroidPushPlatform({MethodChannel? channel})
    : _channel = channel ?? const MethodChannel('net.vpush/push');

  final MethodChannel _channel;

  @override
  Future<AndroidPushDevice?> getDevice() async {
    final raw = await _channel.invokeMethod<Object?>('getDeviceInfo');
    if (raw is! Map) return null;
    final installationId = '${raw['installationId'] ?? ''}';
    if (installationId.isEmpty) return null;
    return AndroidPushDevice(
      installationId: installationId,
      provider: '${raw['provider'] ?? 'none'}',
      token: '${raw['token'] ?? ''}',
      deviceModel: '${raw['deviceModel'] ?? ''}',
      appVersion: '${raw['appVersion'] ?? ''}',
    );
  }

  @override
  Future<bool> requestPermission() async =>
      await _channel.invokeMethod<bool>('requestNotifications') ?? false;
}

class PushRegistrationService {
  PushRegistrationService({required this.api, AndroidPushPlatform? platform})
    : platform = platform ?? MethodChannelAndroidPushPlatform();

  final ApiClient api;
  final AndroidPushPlatform platform;
  String? _installationId;

  Future<bool> registerCurrentDevice() async {
    AndroidPushDevice? device;
    try {
      device = await platform.getDevice();
    } on Object {
      return false;
    }
    if (device == null ||
        device.token.trim().isEmpty ||
        device.installationId.trim().isEmpty) {
      return false;
    }
    _installationId = device.installationId;
    try {
      await api.putJson(
        '/me/android-devices/${device.installationId}',
        body: {
          'token': device.token,
          'provider': device.provider,
          'device_model': device.deviceModel,
          'app_version': device.appVersion,
        },
      );
      return true;
    } on ApiException {
      return false;
    }
  }

  Future<bool> unregisterCurrentDevice() async {
    String? installationId = _installationId;
    if (installationId == null) {
      try {
        installationId = (await platform.getDevice())?.installationId;
      } on Object {
        return false;
      }
    }
    if (installationId == null || installationId.trim().isEmpty) return false;
    try {
      await api.deleteJson('/me/android-devices/$installationId');
      _installationId = null;
      return true;
    } on ApiException {
      return false;
    }
  }
}
