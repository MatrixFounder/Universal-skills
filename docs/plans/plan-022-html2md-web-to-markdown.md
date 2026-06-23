# PLAN 022 — `html2md` (Web/HTML → Markdown) — Stub-First

Maps **TASK 022** R1–R8 onto an atomic Stub-First bead chain for the NEW
`skills/html2md/` skill. Architecture: `docs/ARCHITECTURE.md` (TASK 022).
**License:** Proprietary (embeds docx/pdf code — ARCH §9 / CLAUDE.md §3).

**Phasing (`tdd-stub-first`):**
- **Phase 1 (Stub + RED tests + replication):** bead **022-01** freezes the
  public surface, replicates the two gated clusters, and lays RED tests.
- **Phase 2 (Logic, Green):** beads **022-02…06** fill each Functional
  Component behind the frozen surface, tightening the Phase-1 tests.
- **Integration + Docs:** bead **022-07** ships SKILL.md/license/CI gates.

## Replication note (LOAD-BEARING — ARCH §9, CLAUDE.md §2)

This task **is** a replication event (the repo's first **two-master** skill).
No bead may edit a gated master's source semantics; beads **copy** masters and
the guards live at **022-01** (G-2 smoke) and **022-07** (G-1 `diff -q`, G-4 CI).

| Gated unit | Master | Bead that lands the copy |
|---|---|---|
| `html2md_core.js` | **docx** (`docx2md.js` `buildTurndown`+`expandTableToGrid`) | 022-03 (with G-3 docx no-drift) |
| `web_clean/{archives,reader_mode,preprocess,dom_utils,normalize_css}.py` | **pdf** (`html2pdf_lib/`) | 022-01 |
| EXCLUDED: `render.py`, `chrome_engine.py`, pkg `__init__.py` | — | **never copied** |
| `web_clean/__init__.py` (thin, html2md-owned, NOT gated) | html2md | 022-01 |
| `_errors.py`, `_venv_bootstrap.py` | **docx** | 022-01 (4→**5**-skill) |

## Stub-First ordering (beads)

- **022-01 — [R6/R7 scaffold + IR] Skeleton + replication + RED tests.**
  `skills/html2md/` scaffold via `init_skill.py`; `scripts/` package + thin
  shim (`_venv_bootstrap` prelude); frozen CLI surface (ARCH §5.1), exit-map,
  `_AppError` hierarchy, IR dataclasses (`AcquireResult`/`CleanResult`);
  **replicate** `web_clean/*` (pdf) + thin `web_clean/__init__.py`,
  `_errors.py`+`_venv_bootstrap.py` (docx, 4→5); FC-1/2/3/4 as **stubs**;
  **G-2 import smoke-test** (import `web_clean.archives`+`web_clean.reader_mode`
  → `weasyprint`/`playwright` absent from `sys.modules`); RED E2E/unit
  scaffolding. → [task-022-01](docs/tasks/task-022-01-skeleton-replication-tests.md)
- **022-02 — [R1c–e] FC-1 `acquire.py` OFFLINE paths.** file read + archive
  dispatch (`web_clean/archives.py`, `--archive-frame`) + format/magic-byte
  detection → `AcquireResult`; **zero network** (I-3). →
  [task-022-02](docs/tasks/task-022-02-acquire-offline.md)
- **022-03 — [R3] FC-3 core lift + Node bridge.** Extract
  `htmlToMarkdown(html)→md` into `html2md_core.js` (verbatim from
  `docx2md.js`); wire `docx2md.js` to import it; FC-5 Node bridge
  (`node html2md_core.js`, stdin→stdout); **G-3 docx no-drift** regression
  (AC-R3). → [task-022-03](docs/tasks/task-022-03-core-lift-node-bridge.md)
- **022-04 — [R2] FC-2 `web_clean` wiring.** `preprocess_html` (whole) +
  `reader_mode_html` (reader) → `CleanResult`; AC-R2 reader-needle test on an
  SPA fixture. → [task-022-04](docs/tasks/task-022-04-web-clean-wiring.md)
- **022-05 — [R4/R5] FC-4 `emit.py` (MVP gate).** YAML frontmatter +
  `--download-images`→`_attachments/` (sha1-dedup, relative links) +
  dual-output (`<slug>.md`+`<slug>.reader.md`, `--no-reader`) + stdout +
  `--json-errors`. **MVP gate** = offline file/archive → dual MD. →
  [task-022-05](docs/tasks/task-022-05-emit-obsidian.md)
- **022-06 — [R1a–b] FC-1 URL fetch.** `httpx`+`trafilatura` lite (+ frontmatter
  metadata) + Chrome `auto`-fallback (soft-optional) + SSRF/DoS caps
  (`--max-bytes`/`--max-images`) + exit-3/10. →
  [task-022-06](docs/tasks/task-022-06-acquire-url-fetch.md)
- **022-07 — [R7/R8] Integration + docs + gates.** `SKILL.md`,
  `references/html-to-markdown.md`, per-skill `LICENSE`/`NOTICE`,
  `THIRD_PARTY_NOTICES.md`, `install.sh --with-chrome`, backlog html2md-1…5 →
  done; **G-1 `diff -q` + G-2 + `validate_skill.py` ×5 + (G-4) CI gate**;
  dogfood real URL + `.webarchive` + `.mhtml`. →
  [task-022-07](docs/tasks/task-022-07-docs-integration-gates.md)

## RTM → Bead checklist (mandatory RTM linking, one RTM item per line)

- [ ] **[R1]** Input acquisition — **022-02** (offline c–e) + **022-06** (URL a–b)
- [ ] **[R2]** HTML cleaning (reader-mode + preprocess) — **022-04**
- [ ] **[R3]** HTML→Markdown core (turndown lift) — **022-03**
- [ ] **[R4]** Obsidian emit (frontmatter + `_attachments` + dual-output) — **022-05**
- [ ] **[R5]** Agent-step contract (stdout + `--json-errors`) — **022-05**
- [ ] **[R6]** Fork-free two-master replication — **022-01** (copies) + **022-07** (G-1/G-2/G-4)
- [ ] **[R7]** Skill packaging & isolation — **022-07**
- [ ] **[R8]** CI fork-gate (post-MVP) — **022-07**

## MVP gate

**022-01…05** = offline `file`/`.webarchive`/`.mhtml` → dual Markdown +
frontmatter + `_attachments/`, no network. **022-06 (URL)** is MVP but the
Chrome fallback is engine-soft-optional (lite path always available).

## Acceptance (rolls up TASK 022 §4 + ARCH §9 guards)

- [ ] **AC-R1** offline determinism (archive → MD, zero network) — 022-02/05
- [ ] **AC-R2** reader needle (body present, nav/sidebar absent) — 022-04
- [ ] **AC-R3** docx round-trip byte-identical before/after core lift (G-3) — 022-03
- [ ] **AC-R4** `--download-images` → `_attachments/<sha1>`; `--no-` keeps URLs; dual-output default — 022-05
- [ ] **AC-R5** `--json-errors` envelope; stdout-only on success — 022-05
- [ ] **AC-R6** `diff -q` silent (G-1) + smoke-test (G-2) — 022-01/07
- [ ] **AC-R7** `validate_skill.py skills/html2md` exit 0; `.skill` runs isolated — 022-07
- [ ] **G-4** CI `diff -q` gate + html2md in skill matrix (post-MVP) — 022-07

**No auto-commit** (per `/vdd-*`). Each Phase-2 bead runs an adversarial
logic+security roast before being declared done.
