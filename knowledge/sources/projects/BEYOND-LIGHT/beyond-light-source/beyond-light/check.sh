#!/data/data/com.termux/files/usr/bin/sh
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
gradle --offline --no-daemon verifyCore verifyIntegrationCore
