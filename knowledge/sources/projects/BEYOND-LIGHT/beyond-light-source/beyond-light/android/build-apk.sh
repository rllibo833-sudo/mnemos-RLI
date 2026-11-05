#!/data/data/com.termux/files/usr/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
SDK_ROOT=${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/.local/android-sdk}}
PLATFORM=${ANDROID_PLATFORM:-android-36}
BUILD_TOOLS=${ANDROID_BUILD_TOOLS:-36.0.0}
ANDROID_JAR="$SDK_ROOT/platforms/$PLATFORM/android.jar"
if [ ! -f "$ANDROID_JAR" ]; then echo "Missing Android platform: $ANDROID_JAR" >&2; exit 2; fi
for t in javac d8 aapt2 zipalign apksigner python3 keytool; do command -v "$t" >/dev/null 2>&1 || { echo "Missing required tool: $t" >&2; exit 2; }; done
OUT="$ROOT/build/android-apk"
CLASSES="$OUT/classes"; DEX="$OUT/dex"; ASSETS="$OUT/assets"; RES="$OUT/res-compiled.zip"
mkdir -p "$CLASSES" "$DEX" "$ASSETS/data" "$OUT/generated"
# Preserve existing local research archives in a first-install seed; the app copies them once into private storage.
for f in experiments.jsonl benchmarks.jsonl materials.jsonl published_experiments.jsonl material_curves.jsonl; do if [ -f "$ROOT/data/$f" ]; then cp "$ROOT/data/$f" "$ASSETS/data/$f"; fi; done
find "$CLASSES" -type f -name '*.class' -delete
find "$DEX" -type f -delete
find "$ROOT/src/main/java" "$ROOT/android/src/main/java" -type f -name '*.java' > "$OUT/sources.txt"
javac --limit-modules java.base -source 17 -target 17 -classpath "$ANDROID_JAR" -d "$CLASSES" @"$OUT/sources.txt"
find "$CLASSES" -type f -name '*.class' > "$OUT/class-files.txt"
d8 --min-api 35 --lib "$ANDROID_JAR" --output "$DEX" @"$OUT/class-files.txt"
aapt2 compile --dir "$ROOT/android/src/main/res" -o "$RES"
aapt2 link --auto-add-overlay -I "$ANDROID_JAR" --manifest "$ROOT/android/src/main/AndroidManifest.xml" -R "$RES" -A "$ASSETS" --java "$OUT/generated" --min-sdk-version 35 --target-sdk-version 36 --version-code 1 --version-name 0.4.0 -o "$OUT/unsigned.apk"
python3 - "$OUT/unsigned.apk" "$DEX/classes.dex" <<'PY'
import sys, zipfile
apk, dex = sys.argv[1:]
with zipfile.ZipFile(apk, 'a', compression=zipfile.ZIP_DEFLATED) as z:
    z.write(dex, 'classes.dex')
PY
zipalign -f 4 "$OUT/unsigned.apk" "$OUT/aligned.apk"
KEY="$OUT/local-debug.keystore"
if [ ! -f "$KEY" ]; then keytool -genkeypair -keystore "$KEY" -storepass android -keypass android -alias beyondlight -dname 'CN=BEYOND LIGHT Local Debug,O=BEYOND LIGHT,C=ID' -keyalg RSA -keysize 2048 -validity 10000 >/dev/null 2>&1; fi
apksigner sign --ks "$KEY" --ks-key-alias beyondlight --ks-pass pass:android --key-pass pass:android --out "$OUT/beyond-light-debug.apk" "$OUT/aligned.apk"
apksigner verify --verbose --print-certs "$OUT/beyond-light-debug.apk"
aapt dump badging "$OUT/beyond-light-debug.apk" | head -12
printf 'APK: %s\n' "$OUT/beyond-light-debug.apk"
