# Reddit launch drafts

These are English drafts for the creator to post. They disclose authorship and the unofficial integration. They have not been submitted to Reddit. The first binary release targets Apple silicon with macOS Tahoe 26 or newer; do not describe it as supporting every Mac.

Check each community's current rules, required flair and designated promotion thread before posting. Reddit's rules endpoints returned HTTP 403 during preparation, so these drafts do not imply moderator approval. Use a screenshot with synthetic data, such as `docs/screenshots/this-week.png`, and keep personal lecture media and account details out of screenshots.

## r/notebooklm

**Title:** I built a Mac app that sorts lecture recordings into NotebookLM notebooks by course and week

**Body:**

I made voiceNotebook to handle the work between recording a lecture and getting it into the right NotebookLM notebook. I'm the developer; it's free and open source.

You give it your timetable and connect Apple Voice Memos or a folder of exported audio. It matches recordings to classes, converts them to MP3, and creates or reuses a notebook for each course and week. Two lectures for the same course in week 5 go into the same notebook.

You can also gather those weekly sources into an all-weeks course notebook. Timetable photos are recognized locally on the Mac, with an editable review before saving. Lecture photos need your approval before upload.

Install with Homebrew:

```sh
brew install --cask edyx0/tap/voicenotebook
```

The first packaged release is for Apple silicon on macOS Tahoe 26 or newer. Homebrew installs the audio tools; you don't need to clone the repo or set up Python.

This is an independent project using the unofficial notebooklm-py client, so Google sign-in or uploads may break if Google changes things. Files you upload go to Google's NotebookLM service. Your original recordings stay untouched.

Code, screenshots and setup: https://github.com/Edyx0/voiceNotebook

If you use NotebookLM for lectures, do you keep a notebook per week or one for the whole course? I'd like to hear where this workflow falls short.

## r/macapps

**Title:** [Free, open source] voiceNotebook: organize Voice Memos by class and send lectures to NotebookLM

**Body:**

I'm the developer of voiceNotebook, a Mac app for people who record lectures and use NotebookLM to study.

It reads Apple Voice Memos or a folder you choose, matches recordings against your timetable, and shows them by course and semester week. You can listen locally, review uncertain matches, and upload to weekly NotebookLM notebooks. It also supports an all-weeks notebook for each course.

The timetable can come from a photo: Apple Vision reads it on your Mac, then you edit and save the result. You can add lecture images through Files or the system Photos picker and review them before upload.

```sh
brew install --cask edyx0/tap/voicenotebook
```

The packaged release currently supports Apple silicon and macOS Tahoe 26+. Homebrew installs FFmpeg and the app bundles Python. Source-build instructions are available for other Macs.

Voice Memos access needs Full Disk Access. If you'd rather use exported audio, select a folder instead. Originals are never moved, renamed or deleted.

It's free under the MIT license. NotebookLM access requires your Google account, and the integration uses the unofficial notebooklm-py client. Uploads go to Google.

Screenshots and source: https://github.com/Edyx0/voiceNotebook

I'd appreciate feedback on setup and the recording-review screen, especially anything that feels awkward on macOS.

## r/opensource

**Title:** voiceNotebook: an open-source macOS lecture library with timetable matching and NotebookLM uploads

**Body:**

I'm sharing voiceNotebook, an MIT-licensed Mac app I built for organizing recorded lectures and sending them to NotebookLM.

It matches Apple Voice Memos or exported audio to an editable timetable, converts recordings to MP3, and creates or reuses notebooks by course and week. It keeps upload progress so an interrupted session can resume. Ambiguous recording matches need review, and photo uploads always need approval.

The app uses an AppKit shell with a WKWebView interface, a local Python service, Apple Vision for timetable OCR, and notebooklm-py for the unofficial Google integration. Homebrew manages FFmpeg. The release bundles Python and does not bundle a browser.

```sh
brew install --cask edyx0/tap/voicenotebook
```

The first binary release supports Apple silicon on macOS Tahoe 26+. The repo also includes source-build instructions and isolated tests that don't need a real Google account.

Local organization and playback happen on your Mac. NotebookLM uploads require a Google account and send the selected media to Google; this isn't an offline AI app. Google can change or break the unofficial integration.

Repository: https://github.com/Edyx0/voiceNotebook

Contributions and bug reports are welcome. Reports about failed sign-in or uploads are particularly useful, but please remove account details, cookies and lecture content from logs.

## Short version for a community's promotion thread

I built **voiceNotebook**, a free, open-source Mac app that matches lecture recordings to a timetable and uploads them to NotebookLM notebooks by course and week. It reads Voice Memos or exported audio, supports locally recognized timetable photos, and lets you review lecture images before uploading them.

Install: `brew install --cask edyx0/tap/voicenotebook`

First binary release: Apple silicon, macOS Tahoe 26+. Uses an unofficial NotebookLM client; uploaded media goes to Google. Originals stay untouched.

Source and screenshots: https://github.com/Edyx0/voiceNotebook
