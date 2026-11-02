#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
PROJECT_ROOT="$PWD"
ARCH="$(uname -m)"
PYTHON="${VOICE_NOTEBOOK_PYTHON:-.venv/bin/python}"
APP="dist/voiceNotebook.app"
SIGNING_IDENTITY="${VOICE_NOTEBOOK_SIGNING_IDENTITY:-}"
if [ -z "$SIGNING_IDENTITY" ] && [ -d "$HOME/Applications/voiceNotebook.app" ]; then
  SIGNING_IDENTITY="$(codesign -dv --verbose=4 "$HOME/Applications/voiceNotebook.app" 2>&1 | sed -n 's/^Authority=//p' | head -n 1)"
fi
SIGNING_IDENTITY="${SIGNING_IDENTITY:--}"
PYINSTALLER_ARGS=(--noconfirm --clean)
SIGNING_ARGS=(--force --deep)
if [ "${VOICE_NOTEBOOK_EXTERNAL_FFMPEG:-0}" != "1" ]; then
  PYINSTALLER_ARGS+=(--add-binary "$(command -v ffmpeg):bin" --add-binary "$(command -v ffprobe):bin")
fi
if [[ "$SIGNING_IDENTITY" == "Developer ID Application:"* ]]; then
  PYINSTALLER_ARGS+=(--codesign-identity "$SIGNING_IDENTITY")
  SIGNING_ARGS+=(--options runtime --timestamp --entitlements mac/Release.entitlements)
fi
mkdir -p build
xcrun swiftc mac/TimetableOCR.swift -o build/timetable-ocr -framework Vision -framework ImageIO -target "$ARCH-apple-macosx13.0"
"$PYTHON" -m PyInstaller --onedir --name voice-notebook-server \
  --distpath build/backend-dist --workpath build/pyinstaller --specpath build \
  --add-data "$PROJECT_ROOT/web:web" --collect-all notebooklm --exclude-module playwright \
  --recursive-copy-metadata notebooklm-py --collect-all rookie_cookies --collect-data certifi \
  --add-binary "$PROJECT_ROOT/build/timetable-ocr:bin" \
  "${PYINSTALLER_ARGS[@]}" voice_notebook.py
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp mac/Info.plist "$APP/Contents/Info.plist"
if [ -n "${VOICE_NOTEBOOK_VERSION:-}" ]; then
  [[ "$VOICE_NOTEBOOK_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo "Version must be MAJOR.MINOR.PATCH" >&2; exit 1; }
  /usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VOICE_NOTEBOOK_VERSION" "$APP/Contents/Info.plist"
  /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $VOICE_NOTEBOOK_VERSION" "$APP/Contents/Info.plist"
fi
cp LICENSE "$APP/Contents/Resources/LICENSE.txt"
rm -rf "$APP/Contents/Resources/backend"
cp -R build/backend-dist/voice-notebook-server "$APP/Contents/Resources/backend"
if [[ "$SIGNING_IDENTITY" == "Developer ID Application:"* ]]; then
  # PyInstaller's onedir layout signs Python's binary but leaves its framework unsealed.
  codesign --force --sign "$SIGNING_IDENTITY" --options runtime --timestamp "$APP/Contents/Resources/backend/_internal/Python.framework"
  codesign --verify --deep --strict "$APP/Contents/Resources/backend/_internal/Python.framework"
fi
rm -rf "$APP/Contents/Resources/browser"
xcrun swiftc mac/VoiceNotebook.swift mac/PhotosScanner.swift mac/PhotoDocument.swift mac/GalleryPicker.swift mac/GoogleSignIn.swift -o "$APP/Contents/MacOS/voiceNotebook" \
  -framework AppKit -framework WebKit -framework AuthenticationServices -framework Photos -framework PhotosUI -framework SwiftUI -framework Vision -framework CryptoKit -target "$ARCH-apple-macosx13.0"
xcrun swift mac/Icon.swift "$APP/Contents/Resources/AppIcon.icns"
codesign --sign "$SIGNING_IDENTITY" "${SIGNING_ARGS[@]}" --identifier com.edizy.voiceNotebook "$APP"
codesign --verify --deep --strict "$APP"
echo "Built: $APP"
