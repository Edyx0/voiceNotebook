# macOS releases

The Homebrew tap is [Edyx0/homebrew-tap](https://github.com/Edyx0/homebrew-tap). Its cask downloads a versioned ZIP from this repository's GitHub Releases and verifies its SHA-256. Users run:

```sh
brew install --cask edyx0/tap/voicenotebook
```

The initial release targets Apple silicon and macOS 26 or newer. Homebrew owns FFmpeg and its dependencies; the release does not redistribute those binaries. Source builds retain their existing bundled-audio behavior.

## Build and notarize

Install the build and development requirements and Playwright's test browser as described in the README. A Developer ID Application certificate and its private key must be in the local keychain. Keep signing credentials out of Git and GitHub release assets.

Store notarization credentials interactively once; enter the app-specific password at the prompt, never in a command argument:

```sh
xcrun notarytool store-credentials voiceNotebook --apple-id YOUR_APPLE_ID --team-id YOUR_TEAM_ID
```

Then build, smoke-test, notarize, staple and verify a release:

```sh
VOICE_NOTEBOOK_SIGNING_IDENTITY="Developer ID Application: Your Name (TEAMID)" bash mac/package.sh 0.1.0
```

`VOICE_NOTEBOOK_NOTARY_PROFILE` can select an existing keychain profile instead of `voiceNotebook`. The script stops on any failed check. Its output is `dist/voiceNotebook-VERSION-arm64.zip` and a SHA-256 file. It does not publish automatically.

If Apple's service takes too long or the connection stops, inspect `xcrun notarytool history --keychain-profile voiceNotebook`. Check the submitted request with `notarytool info` or `notarytool log` before resubmitting. Only publish an Accepted submission after stapling and Gatekeeper assessment succeed. Stapling changes the app, so recompute the ZIP and checksum afterward.

## Publish

1. Commit and push the tested source. Create a matching version tag on that commit.
2. Create a GitHub Release for that tag. Attach only the final ZIP and its SHA-256 file. Record architecture, OS minimum, FFmpeg dependency, sign-in requirements and relevant limitations in the release notes.
3. Update `Casks/voicenotebook.rb` in the tap with the version and final archive checksum. Keep the versioned download URL; do not use a mutable latest-download URL or `sha256 :no_check`.
4. Run `brew style --cask Casks/voicenotebook.rb`, `brew fetch --cask edyx0/tap/voicenotebook`, and an install check with an isolated `--appdir`. Confirm the installed bundle's version, signature, notarization ticket and launch.
5. Commit and push the tap update. Verify both repositories' remote commits and the public release download before announcing availability.

The tap intentionally has no `zap` rule: uninstalling must not delete the user's lecture library, account session, timetable or recordings.
