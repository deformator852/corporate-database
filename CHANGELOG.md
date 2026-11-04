# Changelog

What each version of Corpus changes. The installed version is shown on the
**System status** page and recorded in every backup's `manifest`.

## Unreleased

* Corpus is now open source, under the Apache License 2.0.
* The interface moved to daisyUI, with a light and a dark mode. Custom themes
  must be rewritten with daisyUI's variables: the extension API is now version 2.

## 1.0.0 — 2026-10-19

The first release.

* Documents: upload PDF, Word, OpenDocument, Excel, CSV, JSON, XML, Markdown
  and plain text, with four access levels; processing followed live, with
  notifications.
* AI assistant: answers from the company's documents with their sources,
  through a local model in Ollama; chat history, ratings and review.
* Security: encryption at rest with the company's key (in `backend/.env` or
  HashiCorp Vault), key rotation, role-based permissions, audit log, single
  sign-on (OpenID Connect).
* Operations: guided `install` and `configure`, one production script
  (`deploy/deploy.sh`), encrypted backups, document files on the server or in
  the company's S3 storage, moved between them by `configure`, embedding
  model switch and index rebuild from the **System status** page.
* Interface in English, Spanish and French.
