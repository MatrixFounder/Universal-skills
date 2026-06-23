# Architecture Review — TASK 023 (`docs/ARCHITECTURE.md` §15)

- **Date:** 2026-06-23
- **Reviewer:** Orchestrator-as-Architecture-Reviewer (sequential role-switch fallback —
  independent `architecture-reviewer` subagent blocked by a platform 529/classifier outage
  at review time; rerun when infra recovers).
- **Checklist:** `architecture-review-checklist`.
- **Status (rev 1):** APPROVED WITH COMMENTS → **Status (rev 2, after fixes): APPROVED**.
- **has_critical_issues:** false

## General assessment

§15 is a coherent, minimal delta on the real `acquire.py`: a small provider record (no
class hierarchy) + a fetch-ladder wrapper around the existing engines, all in html2md-owned
files, no new dependency. The fork-free claim is **confirmed**. Data-model and security
gaps around the two new sub-features (multi-result search, trust-markdown) and request-URL
construction were found and **fixed in rev 2**. No 🔴 blocking.

## 🔴 CRITICAL
_None._

## 🟡 MAJOR (all resolved in rev 2)

- **A-1 — search multi-result data model.** §4.1 `AcquireResult` is single-valued, but R9
  `--search` produces N results. **Fix applied:** §15.5 now specifies search yields a
  **list** of `AcquireResult`s with an emit loop (one note per result, shared
  `_attachments/`, per-result skip-on-fail).
- **A-2 — trust-markdown data path.** `--remote-format markdown` bypasses the HTML
  pipeline, but §4.1 assumes HTML and the bypass wasn't specified. **Fix applied:** §15.5
  adds `AcquireResult.content_kind ∈ {html, markdown}`; for `markdown`, `cli.convert`
  bypasses FC-2/FC-3 and applies only frontmatter + image localization (no reader variant).
- **A-3 — request-URL injection guard (security).** Building `base + target` (and
  `searchbase + query`) by literal concatenation with an untrusted target/query risks
  request-splitting / header injection / SSRF-via-injection. **Fix applied:** §15.6 now
  mandates URL-encoding the target/query and rejecting CRLF/control chars (the base is
  operator-trusted; the target is validated http(s)+public first).

## 🟢 MINOR (resolved)

- **A-4 — image localization SSRF.** Clarified in §15.6 that localizing images from a
  reader's returned Markdown/HTML reuses `_resolve_url_image`→`_http_get_bytes`, so every
  image URL passes the per-hop public-IP gate (a reader can't smuggle an internal image
  URL).
- **A-5 — latency bound.** §15.2 now states each tier is bounded by the existing
  per-request timeout; worst-case ladder latency = Σ attempted tiers (serial v1).

## Checklist verdict

- **TASK compliance:** UC-1…6 all have an architectural home (ladder, provider layer,
  search provider, emit loop). ✓
- **Data model (CRITICAL):** engine enum extended; `FetchFailed.details.tried` trace;
  `content_kind`; search list-IR — complete after A-1/A-2. ✓
- **System design / YAGNI:** provider = small record (not over-engineered); two search
  shapes justified; SRP between provider-construction / ladder / classification. ✓
- **Doc size / no drift:** `ARCHITECTURE.md` ~680 lines (< 1500); single living document,
  §15 appended (no per-task snapshot files). ✓
- **Security:** SSRF target-gate before remote (closes the real `_fetch_jina_html`
  scheme-only gap); injection guard (A-3); image SSRF (A-4); env-based tokens, no
  hardcoded secrets. ✓
- **Scalability/reliability:** ladder + existing retry/backoff; per-tier timeout bound;
  serial v1 bounded by `--max-results`. ✓
- **Fork-free:** CONFIRMED — `acquire.py`/`cli.py` not in G-1/G-2 gate; no master byte
  change; gate green by construction.

## Final recommendation

**PROCEED to /vdd-plan.** Architecture §15 approved; consistent with the revised TASK 023.
Suggested bead chain (§15.9, 023-01…07) is buildable on the real `acquire.py` without a
rewrite.

---

## Independent rerun (2026-06-23, platform recovered)

The independent `architecture-reviewer` subagent ran on rev 2: **APPROVED WITH COMMENTS**,
`has_critical_issues: false`. It confirmed the fork-free claim against `test_e2e.sh` and
the four self-review fixes (A-1…A-4), and surfaced three 🟡 + minors, **folded into rev 3**:
- **M-1** image-SSRF claim tightened to a hard invariant ("must go through `_http_get_bytes`;
  gated-out image dropped via `None`, never fatal") → §15.6 + 023-05 acceptance (TC-05-06);
- **M-2** search emit names the `emit._frontmatter` `query:` extension + a separate
  `run_search` entrypoint (no union return) → 023-06;
- **M-3** `--engine remote` with no configured provider = usage error (exit 2), never a
  silent jina fall-back → §15.3 + 023-01 (TC-01-07);
- minors: `_DEFAULT_TARGET_SELECTOR` single constant (023-05); `tried` entries carry no URL
  (§15.6); `content_kind`/`markdown` are defaulted frozen-dataclass fields (back-compatible).
**Net: APPROVED.**
