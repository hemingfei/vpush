#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
app_dir="${script_dir}/../mobile/flutter_app"
api_base_url="${API_BASE_URL:-https://vpush.net}"

cd "${app_dir}"
flutter pub get
dart format --output=none --set-exit-if-changed lib test
# Flutter 3.47.2's LSP framing miscounts UTF-8 bytes for non-ASCII paths.
dart analyze
flutter test
flutter build apk --release --split-per-abi \
  --target-platform android-arm,android-arm64 \
  --dart-define="API_BASE_URL=${api_base_url}"

output_dir="build/app/outputs/flutter-apk"
version_name="${FLUTTER_BUILD_NAME:-$(sed -n 's/^version: *//p' pubspec.yaml | cut -d+ -f1)}"
v7_apk="${output_dir}/vpush-${version_name}-armv7.apk"
arm64_apk="${output_dir}/vpush-${version_name}-arm64.apk"
cp "${output_dir}/app-armeabi-v7a-release.apk" "${v7_apk}"
cp "${output_dir}/app-arm64-v8a-release.apk" "${arm64_apk}"

verify_abi() {
  local apk="$1"
  local expected="$2"
  test -s "${apk}"
  local libraries
  libraries="$(unzip -Z1 "${apk}" | sed -E -n 's#^lib/([^/]+)/.*#\1#p' | sort -u)"
  if [[ "${libraries}" != "${expected}" ]]; then
    printf 'Unexpected ABI set in %s: %s (expected %s)\n' "${apk}" "${libraries//$'\n'/,}" "${expected}" >&2
    exit 1
  fi
  local checksum
  if command -v sha256sum >/dev/null 2>&1; then
    checksum="$(sha256sum "${apk}" | cut -d' ' -f1)"
  else
    checksum="$(shasum -a 256 "${apk}" | cut -d' ' -f1)"
  fi
  printf '%s  %s\n' "${checksum}" "${apk}"
}

verify_abi "${v7_apk}" "armeabi-v7a"
verify_abi "${arm64_apk}" "arm64-v8a"

printf 'Built:\n  %s\n  %s\n' \
  "${v7_apk}" \
  "${arm64_apk}"
