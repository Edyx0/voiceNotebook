# voiceNotebook

A local Mac tool for a student returning from lectures, sorting recordings at a desk in daylight. The main task is to turn Voice Memos into MP3 sources in the correct weekly NotebookLM notebook.

The timetable is user supplied and editable, never hardcoded. Week 1, timezone, course codes and recurring time slots determine routing. Ambiguous and undated recordings require review. Never guess from file modification time. Preserve originals and resume partial uploads without duplicating confirmed sources.

The primary timetable input is a photo or screenshot, recognized locally using Apple Vision. Show editable extracted lecture rows and clearly identify unreadable fields. Manual entry remains available. Importing a photo must not change saved routing until the user saves setup. Follow Apple Design and the applicable detailed Human Interface Guidelines across interface work.

Open on a current-week overview with the current/next class and measured recording coverage for past classes. Photos access is optional; permissions unlock suggestions inside the audio-upload workflow. Every image still needs approval. Audio-only uploads work without Photos access, and a failed optional photo scan must not undo completed audio uploads. Voice Memos Full Disk Access requires the user's final confirmation in macOS settings.

Product register: functional Mac desktop utility with a quiet studio-archive direction in the supplied industrial palette. Setup, recording queue, notebook results and a clear connection screen. A standalone .app bundles Python, FFmpeg and the existing processing engine; AppKit hosts a WKWebView workspace and native folder chooser. No sample recordings disguised as real data. Google login uses a separate window in the Mac's default browser and verifies a staged session before saving. No browser is bundled or downloaded. macOS browser-session permissions are explained rather than hidden. Credentials and recordings stay outside Git. Quick start is optional; Photos access is requested only when chosen.
