# Contributing

Start with an issue that describes the problem and the smallest useful change. A reproducible case is more useful than a long proposal.

Follow the setup steps in the README, then run:

```sh
.venv/bin/python -m unittest discover -s tests -v
```

Browser tests use generated media, temporary app data and separate NotebookLM storage. Do not use personal recordings, photos, cookies or account sessions as fixtures. Native OCR tests can use a synthetic timetable image through `TIMETABLE_TEST_IMAGE`.

Keep permission requests explicit. Photos must remain optional. Timetable recognition must stay local and editable; never fill in unreadable times. Do not retry a network upload when its outcome is uncertain. Preserve original media.

Use the existing Python modules, browser UI and AppKit shell. No frontend build step is needed. Keep keyboard focus, labels, reduced motion and narrow windows working. Run the signed Mac build when changing native code or packaged assets.

For UI changes, include a screenshot using synthetic data and update the design notes when a shared rule changes. The editable Paper file and current design exports are linked in `docs/design/README.md`.

Keep pull requests focused. Explain the user-visible change, how you checked it, and anything you could not verify.
