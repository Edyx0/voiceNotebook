#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="${1:?Usage: bash mac/package.sh MAJOR.MINOR.PATCH}"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Invalid version" >&2; exit 1; }
: "${VOICE_NOTEBOOK_SIGNING_IDENTITY:?Set your Developer ID Application identity}"
[[ "$VOICE_NOTEBOOK_SIGNING_IDENTITY" == "Developer ID Application:"* ]] || { echo "Developer ID Application identity required" >&2; exit 1; }
PROFILE="${VOICE_NOTEBOOK_NOTARY_PROFILE:-voiceNotebook}"
PYTHON="${VOICE_NOTEBOOK_PYTHON:-.venv/bin/python}"
APP="dist/voiceNotebook.app"
ARCHIVE="dist/voiceNotebook-${VERSION}-$(uname -m).zip"
xcrun notarytool history --keychain-profile "$PROFILE" >/dev/null
export VOICE_NOTEBOOK_VERSION="$VERSION" VOICE_NOTEBOOK_EXTERNAL_FFMPEG=1
bash mac/build.sh
"$PYTHON" -m unittest discover -s tests -p test_packaged.py -v
ditto -c -k --sequesterRsrc --keepParent "$APP" "$ARCHIVE"
xcrun notarytool submit "$ARCHIVE" --keychain-profile "$PROFILE" --wait
xcrun stapler staple "$APP"
xcrun stapler validate "$APP"
spctl --assess --type execute --verbose "$APP"
# Stapling changes the bundle, so publish a fresh archive with its ticket included.
rm "$ARCHIVE"
ditto -c -k --sequesterRsrc --keepParent "$APP" "$ARCHIVE"
(cd dist && shasum -a 256 "$(basename "$ARCHIVE")") > "$ARCHIVE.sha256"
echo "Release ready: $ARCHIVE"
