# Agent Rules — Universal-Skills

This file is the authoritative behavioural contract for agents
(Claude Code, Anthropic Agent SDK, etc.) working in this repository.
It is kept **in lockstep** with [`GEMINI.md`](GEMINI.md) — any rule
added here is added there too. Public-facing project documentation
is in [`README.md`](README.md); contributor protocol is in
[`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md).

---

## 1. Local-development rules

### Package management

- **Python**: Always use `.venv/` virtual environment (per skill).
  Never `pip install` globally.
  ```bash
  cd skills/<skill>/scripts
  python3 -m venv .venv && source .venv/bin/activate
  pip install -r requirements.txt
  ```
- **Node.js**: Always use local `node_modules/` (per skill).
  Never `npm install -g`.
  ```bash
  cd skills/<skill>/scripts && npm install
  ```
- **Bootstrap shortcut** for skills that have one:
  `bash skills/<skill>/scripts/install.sh`. The script creates
  `.venv/` + `node_modules/` and prints install hints for missing
  system tools (LibreOffice, Poppler, pango, …) — it does NOT install
  system tools itself; that's the user's choice.

### Testing

- Tests run through the per-skill venv:
  ```bash
  cd skills/<skill>/scripts
  ./.venv/bin/python -m unittest discover -s <module>/tests
  ```
- Skill structural validation (Gold Standard / CSO):
  ```bash
  python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/<skill>
  ```
  Must exit 0 before declaring any change complete.
- Always run end-to-end on a real fixture from `examples/` or
  `tmp/test-data/`. Don't ship code that hasn't actually run on data.

---

## 2. Office-skills modification protocol — STRICT

`docx`, `xlsx`, and `pptx` share an identical OOXML helper module
(`scripts/office/`) and LibreOffice wrapper (`scripts/_soffice.py`).
The **`docx` skill is the MASTER**. `xlsx` and `pptx` carry
**byte-identical copies** of those files. There is no symlink, no
submodule, no shared import — physical duplication is intentional
(per project plan §"Независимость скиллов": each skill must be
installable and runnable in isolation, including as a packaged
`.skill` archive).

### Rule

When you change ANYTHING under
`skills/docx/scripts/office/` or `skills/docx/scripts/_soffice.py`:

1. **Edit only the docx copy.** Never edit the xlsx or pptx copies.
2. **Run the docx tests** (`office/tests/`) to confirm the change
   works.
3. **Replicate** to xlsx and pptx in the SAME commit:
   ```bash
   rm -rf skills/xlsx/scripts/office skills/pptx/scripts/office
   cp -R skills/docx/scripts/office skills/xlsx/scripts/office
   cp -R skills/docx/scripts/office skills/pptx/scripts/office
   cp skills/docx/scripts/_soffice.py skills/xlsx/scripts/_soffice.py
   cp skills/docx/scripts/_soffice.py skills/pptx/scripts/_soffice.py
   find skills -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
   ```
4. **Verify byte-identity** before committing:
   ```bash
   diff -qr skills/docx/scripts/office skills/xlsx/scripts/office
   diff -qr skills/docx/scripts/office skills/pptx/scripts/office
   diff -q  skills/docx/scripts/_soffice.py skills/xlsx/scripts/_soffice.py
   diff -q  skills/docx/scripts/_soffice.py skills/pptx/scripts/_soffice.py
   ```
   All four must produce no output.
5. **Re-run skill-validator** on all four office skills:
   ```bash
   for s in docx xlsx pptx pdf; do
       python3 .claude/skills/skill-creator/scripts/validate_skill.py skills/$s
   done
   ```

### What counts as an office/ change

In scope (must replicate): everything under
`skills/docx/scripts/office/` (unpack, pack, validate, validators/,
helpers/, shim/, tests/, schemas/README.md, schemas/fetch.sh,
schemas/w3c/) plus `skills/docx/scripts/_soffice.py`.

Out of scope (docx-only, no replication): `skills/docx/scripts/docx_*.py`,
`skills/docx/SKILL.md`, `skills/docx/references/`,
`skills/docx/examples/`, `skills/docx/scripts/package.json`,
`skills/docx/scripts/requirements.txt`, `skills/docx/scripts/install.sh`.

### Anti-patterns — DO NOT

- ❌ Edit `skills/xlsx/scripts/office/foo.py` directly.
- ❌ Replicate from xlsx → docx (always docx is source of truth).
- ❌ Symlink `skills/xlsx/scripts/office -> ../../docx/scripts/office`.
- ❌ Forget to clean `__pycache__` before `diff -qr` (false positives).
- ❌ Replicate without running tests + validator afterwards.

Full protocol with rationale:
[`docs/CONTRIBUTING.md` §3](docs/CONTRIBUTING.md#3-office-skills-modification-protocol-strict).

---

## 3. Behavioural conventions

### Spec-first when explicitly requested

If the user asks for a *specification* / *plan* / *spec* (and not
code), produce the planning artifact (e.g. `implementation_plan.md`
or write to the plan file in `~/.claude/plans/` if in plan-mode) and
**STOP**. Do not start writing code until the user explicitly says
"implement".

### Tests first when the change is non-trivial

For changes >5 lines of business logic, write or update tests in
the relevant `tests/` directory before declaring the work done. Tests
are the contract; passing tests is the verification that the change
behaves as advertised.

### Honest scope, not aspirational

If a feature has a known limitation (e.g. the AF_UNIX shim does NOT
provide cross-process IPC — see
[`skills/docx/scripts/office/shim/lo_socket_shim.c`](skills/docx/scripts/office/shim/lo_socket_shim.c)
file-level comment), document the limitation in the file's docstring
AND lock it in with a regression test (e.g.
`TestShimCrossProcessIPCLimitation`). Do not let documentation
overstate what the code does.

### License hygiene

This repository is Apache-2.0. All third-party material (XSD
schemas from ECMA-376 / Microsoft OSP / W3C, runtime dependencies,
external CLI tools) is attributed in
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md). When you add a
new external dependency, update that file in the same commit.

---

## 4. Reference index for agents working here

- [`README.md`](README.md) — public registry of all skills.
- [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) — full contributor
  protocol (this file is a behavioural summary; CONTRIBUTING is the
  reference).
- [`docs/SKILL_EXECUTION_POLICY.md`](docs/SKILL_EXECUTION_POLICY.md)
  — script-first vs prompt-first; Tier definitions.
- [`docs/Manuals/office-skills_manual.md`](docs/Manuals/office-skills_manual.md)
  — practical guide to docx/xlsx/pptx/pdf.
- [`docs/refactoring-office-skills.md`](docs/refactoring-office-skills.md)
  — historical design rationale for the open-source office-skills
  architecture; do not edit, supersede via `docs/CONTRIBUTING.md`.
- [`.claude/skills/skill-creator/`](.claude/skills/skill-creator/)
  — `init_skill.py` for new skills; `validate_skill.py` for
  Gold-Standard checks.
- [`.claude/skills/skill-validator/`](.claude/skills/skill-validator/)
  — security and structural compliance scanner.
