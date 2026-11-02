# voiceNotebook 0.1.0

First packaged macOS release. Install the app without cloning the source repository or configuring Python:

```sh
brew install --cask edyx0/tap/voicenotebook
```

Open **voiceNotebook** from Applications after installation. The Homebrew tap is [Edyx0/homebrew-tap](https://github.com/Edyx0/homebrew-tap).

## Requirements

- Apple silicon Mac with macOS Tahoe 26 or newer.
- Homebrew, which installs FFmpeg automatically. Python is bundled with the app.
- A Google account with NotebookLM access and an internet connection for uploads.

The app is signed with Developer ID and notarized by Apple. The ZIP includes the stapled notarization ticket. The accompanying `.sha256` file checks the final ZIP.

## Included

- Apple Voice Memos or exported-audio folders, with local playback and timetable matching.
- Editable timetable recognition using Apple Vision on the Mac.
- MP3 conversion and NotebookLM notebooks grouped by course and semester week.
- All-weeks course notebooks and saved upload progress.
- Optional lecture photos and the native Photos picker, with review before upload.

## First launch

Connect recordings, sign in to Google, then review your timetable and recording matches. Voice Memos needs Full Disk Access; selecting a folder of exported recordings avoids that requirement. Photos remain optional. Only enable automatic audio sync if you want scheduled uploads.

This independent app uses the unofficial notebooklm-py client. Google may change sign-in or upload behavior. Uploaded audio and approved images go to Google's NotebookLM service; original recordings stay untouched.

This binary release does not include an Intel build. Source-build instructions remain in the README. The automated tests use isolated data; they do not certify every Google account, browser or permission configuration.
