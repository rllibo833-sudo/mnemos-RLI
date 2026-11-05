# Android build for Termux

> Optional experimental Android/WebView runtime. The default Beyond-Light website is hosted on GitHub Pages and does not require Termux, a local server, or an APK. Android packaging is a separate path and is not covered by Pages deployment. See [architecture](../../../docs/ARCHITECTURE.md) and [implementation status](../../../docs/STATUS.md).

A local APK build is implemented in `build-apk.sh`. It compiles the shared Java core and a loopback-only `HttpServer` compatibility adapter, then packages the existing HTML UI in a native WebView Activity. State is stored in app-private files; the first launch copies the local experiment, benchmark, material, published-experiment, and material-curve seed archives only when absent. No external research backend or cloud account is used.

## Build

Requirements: Java/Javac, Android SDK platform 36, SDK Build Tools 36.0.0, `d8`, Termux `aapt2`, `zipalign`, `apksigner`, `python3`, and `keytool`. Set `ANDROID_SDK_ROOT` if the SDK is not at `$HOME/.local/android-sdk`.

```sh
./android/termux-preflight.sh
./android/build-apk.sh
```

APK output: `build/android-apk/beyond-light-debug.apk`. The script verifies the APK signature and prints package metadata. It uses a local debug key; this is not a store-release signing configuration.

## Runtime limits

The app binds its calculation server to `127.0.0.1` on an ephemeral port. The Android adapter is a deliberately small subset of JDK `HttpServer` and implements the API methods used by `Main`; platform/device runtime testing is still required. The browser uses Android's Storage Access Framework for explicit import/export. Source links open in an external browser only when tapped. A connected device is required for install/launch validation.
