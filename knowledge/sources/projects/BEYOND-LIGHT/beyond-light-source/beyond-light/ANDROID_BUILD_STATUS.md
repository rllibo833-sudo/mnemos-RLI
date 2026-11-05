# Android build status

> This is a separate experimental Android packaging path. It is not required to use the public GitHub Pages website, and it does not describe the website runtime. See [repository architecture](../../docs/ARCHITECTURE.md) and [current implementation status](../../docs/STATUS.md).

The Android packaging path and native WebView adapter are implemented:

- `android/build-apk.sh` compiles the shared Java core together with the Android adapter, packages the existing web UI and local seed data, then aligns and signs a debug APK.
- `android/src/main/java/org/beyondlight/android/MainActivity.java` starts the local calculation server, hosts the UI in WebView, and handles explicit file import/export through Android's Storage Access Framework.
- The adapter stores working data in app-private storage and binds the calculation server to loopback.

## Current verification boundary

The repository's GitHub Actions workflow verifies the Java 21 core, runs `verifyCore`, packages the desktop JAR, and synchronizes the source ZIP. It does **not** install the Android SDK, execute `android/build-apk.sh`, or produce an APK artifact.

The APK build script requires a compatible Android/Termux toolchain: Android platform 36, Build Tools 36.0.0, `javac`, `d8`, `aapt2`, `aapt`, `zipalign`, `apksigner`, `python3`, and `keytool`. The resulting APK uses a local debug key and is not configured for store release.

No successful APK build or connected-device install/launch test is currently recorded in this repository. Device compatibility, lifecycle behavior, and runtime performance therefore remain unverified.

See [android/README.md](android/README.md) for build requirements and commands.
