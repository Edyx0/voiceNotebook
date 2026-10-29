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
mkdir -p build
xcrun swiftc mac/TimetableOCR.swift -o build/timetable-ocr -framework Vision -framework ImageIO -target "$ARCH-apple-macosx13.0"
"$PYTHON" -m PyInstaller --noconfirm --clean --onedir --name voice-notebook-server \
  --distpath build/backend-dist --workpath build/pyinstaller --specpath build \
  --add-data "$PROJECT_ROOT/web:web" --collect-all notebooklm --collect-all playwright \
  --copy-metadata notebooklm-py --collect-all rookie_cookies --collect-data certifi \
  --add-binary "$PROJECT_ROOT/build/timetable-ocr:bin" \
  --add-binary "$(command -v ffmpeg):bin" --add-binary "$(command -v ffprobe):bin" voice_notebook.py
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp mac/Info.plist "$APP/Contents/Info.plist"
rm -rf "$APP/Contents/Resources/backend"
cp -R build/backend-dist/voice-notebook-server "$APP/Contents/Resources/backend"
BROWSER_ROOT="$("$PYTHON" -c 'from pathlib import Path; from playwright.sync_api import sync_playwright; p = sync_playwright().start(); print(Path(p.chromium.executable_path).parents[3]); p.stop()')"
rm -rf "$APP/Contents/Resources/browser"
mkdir -p "$APP/Contents/Resources/browser"
ditto "$BROWSER_ROOT" "$APP/Contents/Resources/browser/$(basename "$BROWSER_ROOT")"
xcrun swiftc mac/VoiceNotebook.swift mac/PhotosScanner.swift mac/PhotoDocument.swift mac/GoogleSignIn.swift -o "$APP/Contents/MacOS/voiceNotebook" \
  -framework AppKit -framework WebKit -framework AuthenticationServices -framework Photos -framework Vision -framework CryptoKit -target "$ARCH-apple-macosx13.0"
xcrun swift mac/Icon.swift "$APP/Contents/Resources/AppIcon.icns"
codesign --force --deep --sign "$SIGNING_IDENTITY" --identifier com.edizy.voiceNotebook "$APP"
codesign --verify --deep --strict "$APP"
echo "Built: $APP"
