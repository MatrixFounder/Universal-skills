# Contributing to Universal-Skills

Quick rules for adding new skills, fixing bugs, and modifying the
Office skills (`docx` / `xlsx` / `pptx` / `pdf`) — which share code
and have a strict replication protocol.

---

## 1. Project layout

```
Universal-skills/
├── LICENSE                          # Apache-2.0 (root; covers everything except the four office skills)
├── THIRD_PARTY_NOTICES.md           # attribution for ECMA/MS/W3C and OSS deps (governs both license scopes)
├── README.md                        # public-facing
├── CLAUDE.md / GEMINI.md            # agent-specific behavioural rules (kept in sync)
├── docs/
│   ├── CONTRIBUTING.md              # this file
│   ├── SKILL_EXECUTION_POLICY.md    # script-first / Tier definitions
│   ├── refactoring-office-skills.md # design plan (historical reference)
│   └── Manuals/
│       └── office-skills_manual.md  # how to use docx/xlsx/pptx/pdf in practice
├── skills/                          # one folder per skill, each self-contained
│   ├── docx/                        # MASTER for the office/ shared module — Proprietary, see LICENSE+NOTICE in this dir
│   ├── xlsx/                        # downstream copy of office/        — Proprietary, see LICENSE+NOTICE in this dir
│   ├── pptx/                        # downstream copy of office/        — Proprietary, see LICENSE+NOTICE in this dir
│   ├── pdf/                         # standalone (no office/ needed)    — Proprietary, see LICENSE+NOTICE in this dir
│   ├── marp-slide/, mcp-builder/, …                                     # Apache-2.0 (root LICENSE)
│   └── …
└── .claude/skills/                  # agent runtime: skill-creator, skill-validator, etc.
```

**Per-skill structure** (Gold Standard, validated by `skill-validator`):

```
skills/<skill>/
├── SKILL.md            # YAML frontmatter + required sections
├── .gitignore          # local artifacts (.venv/, node_modules/, build outputs)
├── references/         # domain knowledge (loaded on demand by the agent)
├── scripts/
│   ├── install.sh      # bootstrap: checks system tools, installs local deps
│   ├── requirements.txt
│   ├── package.json    # if Node deps
│   └── …
└── examples/           # at least one fixture
```

---

## 2. Modifying ANY skill — universal checklist

1. **Edit only inside the target skill folder.** Do not touch sibling
   skills unless your change is explicitly cross-cutting (see §3 for
   the office-skills replication exception).
2. **Use the local `.venv` and `node_modules`** that `install.sh`
   creates. Never `pip install` or `npm install -g` globally.
3. **Add or update tests** for any non-trivial logic. Tests live next
   to the code (`scripts/<module>/tests/test_*.py`). Run with the
   skill's local venv:
   ```bash
   cd skills/<skill>/scripts
   ./.venv/bin/python -m unittest discover -s <module>/tests
   ```
4. **Run the skill-validator** before declaring done:
   ```bash
   python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/<skill>
   ```
   Must exit 0 (✅ Validation PASSED).
5. **Run end-to-end on a real fixture** (something in `examples/` or
   `tmp/test-data/`). Don't ship code that hasn't actually run on data.
6. **Update SKILL.md** if you added a new script, flag, or
   constraint. The Quick Reference table is the agent's primary
   discovery surface.
7. **Update `references/*.md`** if your fix changes a documented
   behaviour or workaround.
8. **Update `.gitignore`** if your change introduces a new local
   artifact (compiled binary, cache directory, lock file).

---

## 3. Office-skills modification protocol (STRICT)

`docx`, `xlsx`, and `pptx` share an identical OOXML helper module:
[`scripts/office/`](../skills/docx/scripts/office/) plus
[`scripts/_soffice.py`](../skills/docx/scripts/_soffice.py).
The `docx` skill is the **MASTER**; `xlsx` and `pptx` carry **byte-
identical copies**. There is **NO symlink, no submodule, no shared
import** — physical duplication is intentional, dictated by the
project plan §"Независимость скиллов" (each skill must be installable
and runnable in isolation, including as a packaged `.skill` file).

### The protocol

When you change ANYTHING under
`skills/docx/scripts/office/` or `skills/docx/scripts/_soffice.py`:

```bash
# 1. Make the edit ONLY in skills/docx/scripts/.
# 2. Run docx tests:
cd skills/docx/scripts
./.venv/bin/python -m unittest discover -s office/tests
cd ../../..

# 3. Replicate to xlsx and pptx — exactly:
rm -rf skills/xlsx/scripts/office skills/pptx/scripts/office
cp -R skills/docx/scripts/office skills/xlsx/scripts/office
cp -R skills/docx/scripts/office skills/pptx/scripts/office
cp skills/docx/scripts/_soffice.py skills/xlsx/scripts/_soffice.py
cp skills/docx/scripts/_soffice.py skills/pptx/scripts/_soffice.py

# 4. Strip pycaches and verify identity:
find skills -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
diff -qr skills/docx/scripts/office skills/xlsx/scripts/office
diff -qr skills/docx/scripts/office skills/pptx/scripts/office
diff -q  skills/docx/scripts/_soffice.py skills/xlsx/scripts/_soffice.py
diff -q  skills/docx/scripts/_soffice.py skills/pptx/scripts/_soffice.py
# All four `diff` invocations MUST produce no output.

# 5. Run skill-validator on all four:
for s in docx xlsx pptx pdf; do
    python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/$s
done
```

### What counts as "office/" change

- `office/unpack.py`, `office/pack.py`, `office/validate.py`
- `office/validators/*.py` (including `redlining.py`, `base.py`, `docx.py`, `xlsx.py`, `pptx.py`)
- `office/helpers/*.py` (`merge_runs.py`, `simplify_redlines.py`)
- `office/shim/lo_socket_shim.c`, `office/shim/build.sh`
- `office/tests/*` (test infrastructure stays in docx but copies travel)
- `_soffice.py` (LibreOffice wrapper)
- `office/schemas/README.md` and `office/schemas/fetch.sh` (NOT the
  `ecma-376/`, `microsoft/` contents — those are gitignored)

### What does NOT trigger replication

- Changes inside `skills/docx/scripts/docx_*.py` (skill-specific scripts)
- Changes inside `skills/docx/SKILL.md`, `skills/docx/references/`,
  `skills/docx/examples/`
- Changes to `skills/docx/scripts/package.json` / `requirements.txt`
- Changes to `skills/docx/scripts/install.sh`

These are docx-specific and stay in docx alone. xlsx and pptx have
their own analogous files.

### Why duplication, not symlink

1. **Self-contained skills**: when packaged via
   `.claude/skills/skill-creator/scripts/package_skill.py`, each skill
   becomes a `.skill` zip archive. Symlinks would dangle.
2. **Different downstream contexts**: a user installing only `pptx`
   skill on another machine should not need `docx` to also be present.
3. **Plan §"Независимость скиллов"**: explicit requirement, debated
   and chosen over a `common/` root module.

### Anti-pattern (do NOT do)

- ❌ Edit `skills/xlsx/scripts/office/foo.py` directly
- ❌ Replicate from xlsx → docx (always docx is the source of truth)
- ❌ Symlink `skills/xlsx/scripts/office -> ../../docx/scripts/office`
- ❌ Forget to clean `__pycache__` before `diff -qr` (false positives)
- ❌ Skip step 5 (validator must pass on all four after replication)

---

## 4. Adding a new skill

Use `skill-creator` (it enforces Gold Standard structure):

```bash
cd .claude/skills/skill-creator/scripts
python3 init_skill.py my-new-skill --tier 2 --path ../../../../skills/
```

Then fill in `SKILL.md`, write scripts, write tests, run validator,
register in `README.md` under the appropriate category.

---

## 5. Documentation pointers

- [SKILL_EXECUTION_POLICY.md](SKILL_EXECUTION_POLICY.md) — when to
  use script-first vs prompt-first; Tier definitions.
- [Manuals/office-skills_manual.md](Manuals/office-skills_manual.md)
  — practical guide to docx/xlsx/pptx/pdf, including the redlining
  validator and the AF_UNIX shim for sandboxed environments.
- [refactoring-office-skills.md](refactoring-office-skills.md) —
  original design plan that drove the office-skills architecture
  (historical reference; do not edit, supersede via this CONTRIBUTING).

---

## 6. Licensing of office skills

The four office skills are governed by their own per-skill
`LICENSE` and `NOTICE` files (effective **2026-04-25**) and **not**
by the root Apache-2.0 license:

- [`skills/docx/LICENSE`](../skills/docx/LICENSE) and [`NOTICE`](../skills/docx/NOTICE)
- [`skills/xlsx/LICENSE`](../skills/xlsx/LICENSE) and [`NOTICE`](../skills/xlsx/NOTICE)
- [`skills/pptx/LICENSE`](../skills/pptx/LICENSE) and [`NOTICE`](../skills/pptx/NOTICE)
- [`skills/pdf/LICENSE`](../skills/pdf/LICENSE)  and [`NOTICE`](../skills/pdf/NOTICE)

Rules:

- **Do not modify or remove** these `LICENSE` / `NOTICE` files in
  any PR. Any change to them must be authored by the copyright
  holder.
- **External pull requests** that touch
  `skills/{docx,xlsx,pptx,pdf}/**` are **not accepted** without a
  prior signed Contributor License Agreement; please open an issue
  first to discuss. Bug reports without code are welcome.
- The `SKILL.md` frontmatter for each office skill must keep
  `license: LicenseRef-Proprietary`. Do not change it back to
  `Apache-2.0`.
- The shared OOXML module under `skills/docx/scripts/office/` (and
  its byte-identical copies in xlsx/pptx) is itself part of the
  proprietary skill; replication still follows the strict protocol
  in [§3](#3-office-skills-modification-protocol-strict).
- Third-party components used by the office skills keep their
  original licenses, attributed in
  [`THIRD_PARTY_NOTICES.md`](../THIRD_PARTY_NOTICES.md) at the repo
  root (linked from each office skill's `NOTICE`). When you add a
  new dependency, update `THIRD_PARTY_NOTICES.md` in the same
  commit.

For licensing inquiries, contact: <kuptsov.sergey@gmail.com>.

---

## 7. Commit hygiene

- One logical change per commit.
- Office-skills replication: replicate in the **same commit** as the
  source `docx` change. CI/reviewer should be able to verify
  `diff -qr` matches at every commit on the main branch.
- Reference the issue / scenario in the commit message.
- Do not commit `node_modules/`, `.venv/`, `__pycache__/`,
  `.pytest_cache/`, `.hypothesis/`, compiled shim binaries, ECMA-376
  schemas, package-lock.json — all are `.gitignore`d (root or
  per-skill).

---

## 8. Quality automation (visual regression, fuzz tests, CI)

Three quality layers run on top of the per-skill E2E suites
([§2.5](#2-modifying-any-skill--universal-checklist)). All three are
designed to soft-skip locally when the host lacks a tool, and to fail
loudly in CI.

### Visual regression — `tests/visual/` ([README](../tests/visual/README.md))

First-page golden-image comparison for every PDF an E2E suite
produces. Pipeline: `pdftoppm` → PNG → `magick compare -metric AE
-fuzz 5%`. Goldens live at `tests/visual/goldens/<skill>/<name>.png`
and are committed.

```bash
# Add a new golden after a deliberate output change:
UPDATE_GOLDENS=1 bash skills/pdf/scripts/tests/test_e2e.sh
git diff tests/visual/goldens/   # review the new/updated PNGs
```

`STRICT_VISUAL=1` (set in CI) makes a missing golden or missing
ImageMagick a hard failure; without it, both warn-and-skip so a
fresh local checkout doesn't break.

### Property-based fuzz — `tests/property/`

Hypothesis-driven black-box fuzz for `md2pdf.py`, `md2docx.js`,
`csv2xlsx.py`. Each test asserts the CLI either exits 0 with non-empty
output, OR exits non-zero **without** a Python traceback / Node
uncaught exception.

```bash
bash tests/property/setup.sh                          # one-time
tests/property/.venv/bin/pytest tests/property -q     # run
HYPOTHESIS_PROFILE=ci tests/property/.venv/bin/pytest tests/property -q
```

Default profile: 30 examples per test (~30 s). `ci` profile: 100
examples (~2 min). Each example runs in its own
`tempfile.TemporaryDirectory()` — pytest's `tmp_path` is
function-scoped and incompatible with `@given`.

### CI — [`.github/workflows/office-skills.yml`](../.github/workflows/office-skills.yml)

Triggers: push to `main`, PRs that touch `skills/{docx,xlsx,pptx,pdf}/`
or `tests/`, plus `workflow_dispatch`. Three job groups:

- **`skill` matrix** (per docx/xlsx/pptx/pdf): `install.sh` →
  `validate_skill.py` → `test_e2e.sh` with `STRICT_VISUAL=1`.
- **`property`** (after skill): hypothesis fuzz under
  `HYPOTHESIS_PROFILE=ci`.
- **goldens regen via `workflow_dispatch`**: dispatch with
  `update_goldens=true` reruns each E2E with `UPDATE_GOLDENS=1` and
  uploads the regenerated PNGs as a per-skill artifact. Download,
  commit, re-push.

Cross-platform note: goldens generated on macOS will likely drift
beyond the 0.5%-pixel default threshold against Ubuntu CI's font
rendering. First CI run on a new branch may need a one-time
`workflow_dispatch` regen.
