#!/data/data/com.termux/files/usr/bin/sh
set -eu
printf 'BEYOND LIGHT Android build preflight\n'
printf 'Gradle: '; command -v gradle || true
printf 'Java: '; java -version 2>&1 | head -1
printf 'ANDROID_HOME: %s\n' "${ANDROID_HOME:-NOT_SET}"
printf 'ANDROID_SDK_ROOT: %s\n' "${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/.local/android-sdk}}"
SDKMANAGER=${ANDROID_SDKMANAGER:-${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/.local/android-sdk}}/cmdline-tools/latest/bin/sdkmanager}
if [ -x "$SDKMANAGER" ]; then printf 'sdkmanager: %s\n' "$SDKMANAGER"; else printf 'sdkmanager: MISSING\n'; fi
for tool in adb aapt aapt2 d8 apksigner zipalign; do
  if command -v "$tool" >/dev/null 2>&1; then printf '%s: %s\n' "$tool" "$(command -v "$tool")"; else printf '%s: MISSING\n' "$tool"; fi
done
sdk=${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/.local/android-sdk}}
if [ -n "$sdk" ]; then
  for f in "$sdk/platforms/android-36/android.jar" "$sdk/build-tools/36.0.0/package.xml"; do
    if [ -f "$f" ]; then printf 'PRESENT %s\n' "$f"; else printf 'MISSING %s\n' "$f"; fi
  done
else
  printf 'MISSING Android SDK platform android.jar and SDK build-tools\n'
fi
printf 'Project Android application module: '
if [ -f "$(dirname "$0")/build-apk.sh" ] && [ -f "$(dirname "$0")/src/main/java/org/beyondlight/android/MainActivity.java" ]; then printf 'manual Android packaging and runtime adapter present\n'; else printf 'MISSING Android packaging/runtime adapter\n'; fi
