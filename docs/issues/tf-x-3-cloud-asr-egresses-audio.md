---
id: TF-X-3
type: known-issue
status: by-design
opened_at: 2026-07-09
category: security
severity: LOW
component: transcript-fetcher
slug: tf-x-3-cloud-asr-egresses-audio
---

# TF-X-3 — cloud ASR egresses audio (opt-in)

> Part of the TRANSCRIPT-FETCHER-X (TASK 026) honest-scope set. Architecture:
> [`docs/architectures/architecture-016-transcript-fetcher-x-asr.md`](../architectures/architecture-016-transcript-fetcher-x-asr.md) §7.

**Status:** open (by design) • **Severity:** LOW • **Location:**
`asr/openai_api.py`. The cloud backend is used **only** with `--asr-allow-cloud`
(or `TRANSCRIPT_FETCHER_ASR_ALLOW_CLOUD=1`) AND a key present; the audio leaves
the machine to the configured endpoint. Disclosed in SKILL.md §5 + `.env.example`.
Local backends are always tried first. **Do-not:** use `--asr-allow-cloud` for
sensitive audio without accepting the egress.
