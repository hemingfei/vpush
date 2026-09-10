#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
app_dir="${script_dir}/../mobile/flutter_app"
api_base_url="${API_BASE_URL:-https://vpush.net}"

cd "${app_dir}"
flutter pub get
dart format --output=none --set-exit-if-changed lib test
flutter analyze
flutter test
flutter build apk --release --split-per-abi \
  --target-platform android-arm,android-arm64 \
  --dart-define="API_BASE_URL=${api_base_url}"

output_dir="build/app/outputs/flutter-apk"
cp "${output_dir}/app-armeabi-v7a-release.apk" "${output_dir}/vpush-${FLUTTER_BUILD_NAME:-$(sed -n 's/^version: *//p' pubspec.yaml | cut -d+ -f1)}-armv7.apk"
cp "${output_dir}/app-arm64-v8a-release.apk" "${output_dir}/vpush-${FLUTTER_BUILD_NAME:-$(sed -n 's/^version: *//p' pubspec.yaml | cut -d+ -f1)}-arm64.apk"

printf 'Built:\n  %s\n  %s\n' \
  "${output_dir}/vpush-${FLUTTER_BUILD_NAME:-$(sed -n 's/^version: *//p' pubspec.yaml | cut -d+ -f1)}-armv7.apk" \
  "${output_dir}/vpush-${FLUTTER_BUILD_NAME:-$(sed -n 's/^version: *//p' pubspec.yaml | cut -d+ -f1)}-arm64.apk"
