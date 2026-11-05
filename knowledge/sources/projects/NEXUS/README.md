# NEXUS for Android

NEXUS is a native, offline-first Android knowledge notebook built with Kotlin, Jetpack Compose and Room/SQLite. The installed APK runs independently; it does not require Termux or a network connection.

## Build a signed release APK in Termux

Requirements: Java 17 or newer, Gradle, Android SDK Platform 36 and Build Tools 36.0.0. Set `ANDROID_HOME` if the SDK is not at `$HOME/.local/android-sdk`, then run:

```sh
./build-release.sh
```

The script creates a private release signing key on first run. Keep both `nexus-release.jks` and `keystore.properties` secure and backed up; they are ignored by Git. Losing them means future app updates cannot replace this signed installation. The APK is created at `app/build/outputs/apk/release/app-release.apk` and can be installed with Android's package installer or `adb install -r`.

To check the available unit-test task, run `gradle testDebugUnitTest`. No network service is used by the app.

## Features

- Create, edit, search, tag and delete Markdown notes with a readable preview.
- Directed manual links, incoming backlinks, and offline term-similarity suggestions.
- Interactive 3D-style knowledge graph with rotate, pan, zoom, note selection, tag and search filters, and inferred overlap edges.
- Attach images, videos, PDFs and ZIP files from Android's document picker; open compatible files with installed Android apps.
- Export notes, links and attachment contents to a portable ZIP backup, then merge-restore by record ID.
- Store notes and attachments persistently in the app's private storage; no network permission is requested.

## Backup and restore

Use **Export** in the app bar and choose a destination for the ZIP. Use **Import** and select a NEXUS ZIP backup to merge its records. Restore does not erase existing records.
