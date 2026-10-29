# Security and privacy reports

For a suspected vulnerability, use this repository's private vulnerability reporting feature. Do not open a public issue with session files, cookies, account details, recordings or photos.

The app binds its service to `127.0.0.1`, checks the request host and requires a per-run token for writes. It has no hosted backend. Google session data is stored locally by `notebooklm-py` and must be treated like a password. Never attach it to an issue or commit it.

Reports are most useful with a minimal reproduction, affected version and impact. Use synthetic data and redact personal paths and identifiers. If a report requires a real session, describe the steps rather than sharing the session itself.

NotebookLM access uses an unofficial client. Google can change its service, authentication or upload behavior. This project cannot grant macOS permissions or bypass Google account checks.
