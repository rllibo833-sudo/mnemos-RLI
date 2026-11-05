#!/data/data/com.termux/files/usr/bin/sh
set -eu
cd "$(dirname "$0")"

if [ ! -f keystore.properties ]; then
    if [ -e nexus-release.jks ]; then
        echo "nexus-release.jks exists but keystore.properties is missing; refusing to replace signing identity." >&2
        exit 1
    fi
    keypass=$(openssl rand -hex 24)
    keytool -genkeypair -keystore nexus-release.jks -storepass "$keypass" -keypass "$keypass" \
        -alias nexus -keyalg RSA -keysize 2048 -validity 10000 \
        -dname 'CN=NEXUS Release, OU=NEXUS, O=NEXUS, L=Jakarta, ST=DKI Jakarta, C=ID' >/dev/null 2>&1
    printf 'storeFile=nexus-release.jks\nstorePassword=%s\nkeyAlias=nexus\nkeyPassword=%s\n' \
        "$keypass" "$keypass" > keystore.properties
    unset keypass
fi

ANDROID_HOME="${ANDROID_HOME:-$HOME/.local/android-sdk}"
ANDROID_SDK_ROOT="$ANDROID_HOME"
export ANDROID_HOME ANDROID_SDK_ROOT
gradle --no-daemon --max-workers=1 assembleRelease
