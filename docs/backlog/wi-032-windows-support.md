---
id: WI-032-windows-support
type: work-item
status: open
effort: L
value: M
source: platform audit of skills/{docx,xlsx,pptx,pdf,html} (2026-08-29, commit c7b0916)
---

# WI-032 — Windows support for the office skills

## Verdict

The five office skills (`docx`, `xlsx`, `pptx`, `pdf`, `html`) do **not** run on native
Windows (`cmd.exe` / PowerShell). They run on WSL2, which is an ordinary Linux host and
is already covered by the existing Ubuntu path.

No contract is broken by this: no `SKILL.md`, `README.md`, or `docs/` page claims Windows
support, and none declares a supported-platform list at all. That absence is the first
defect — a user on Windows learns the answer by hitting `ImportError: No module named
'fcntl'`, not by reading a line of documentation. This is therefore a work-item, not a
known issue.

Failure is not graceful. `bash scripts/install.sh` — the documented **MUST** first step
of every office `SKILL.md` — has no Windows counterpart, so the venv is never created;
and four CLIs abort at import time before any argument is parsed.

## The chain that breaks

Every documented invocation of every office CLI runs the same four-link chain. On
macOS/Linux all four hold. On native Windows the first three break independently, and
they break in the order the chain runs — so fixing one only moves the failure up by one
link. This is why Stage 1 is indivisible.

```
  py -3 scripts\docx_add_comment.py in.docx out.docx --anchor-text "..."
    |
    v
+------------------------------------------------------------------------------+
|  LINK 1  the interpreter starts                                              |
|    ok   POSIX  `python3` is on PATH                                          |
|    WIN  `python3` is not a command (`py -3` / `python`; the Store alias is   |
|         a stub). Documented on 211 SKILL.md lines, hardcoded in md2pptx.js.  |
|         -> A4                                                                |
+------------------------------------------------------------------------------+
|  LINK 2  _venv_bootstrap re-execs into the skill's own venv                  |
|    ok   POSIX  probes `.venv/bin/python`; os.execv replaces the process      |
|    WIN  the interpreter is at `.venv\Scripts\python.exe` - the probe misses, |
|         the re-exec never fires, the CLI runs on the ambient interpreter.    |
|         -> A2                                                                |
|    WIN  and once the path is fixed: os.execv on Windows spawns + exits       |
|         instead of replacing, so the exit code is lost.  -> T1               |
+------------------------------------------------------------------------------+
|  LINK 3  third-party imports resolve from that venv                          |
|    ok   POSIX  `bash install.sh` built it                                    |
|    WIN  no `install.ps1` exists, so there is no venv to resolve from.        |
|         ModuleNotFoundError - or the `run: bash .../install.sh` hint,        |
|         which is itself unrunnable on the host that printed it.  -> A1       |
+------------------------------------------------------------------------------+
|  LINK 4  the work itself                                                     |
|    ok   pure OOXML: portable today (Path.as_posix(), zipfile, lxml)          |
|    WIN  only when the command shells out to LibreOffice / Poppler / GTK      |
|         -> B1-B5, T2                                                         |
+------------------------------------------------------------------------------+
```

Links 1-3 are mutually independent. Ship `install.ps1` alone and the failure moves from
link 3 to link 2; fix the bootstrap alone and it moves to link 1. None of the three is
observable to a user until the two before it are closed, which is also why this audit had
to read the code rather than run it.

### What link 4 costs

Link 4 is where the scope actually splits, and it splits favourably. Of the **47**
production entrypoints (37 Python + 10 Node):

| Link-4 dependency | Count | Entrypoints |
|---|---|---|
| **None** — pure Python / Node | **39** | md↔docx/pptx, `docx2md`, `html2docx`, `obsidian2md`, `office.validate`, `office_passwd`, template fill, merge, replace, anchor, the xlsx suite, PDF merge/split/extract/forms, all of `html` |
| LibreOffice, hard | 4 | `docx_accept_changes`, `xlsx_recalc`, `pptx_to_pdf`, `pptx_thumbnails` |
| LibreOffice + Poppler, hard | 4 | `preview.py` (one copy per office skill) |
| LibreOffice, degrades gracefully | (3 routes) | `docx2md` shape route, `pptx2md` images, `md2pptx --pptx-editable` |

So **39 of 47 entrypoints need nothing from link 4** — for them the whole Windows port is
exactly links 1-3. That is the Stage 1 boundary, and it is what makes Stage 2 (GTK,
Poppler, Tesseract) genuinely optional rather than a hidden prerequisite.

### What this changes about A4

Because link 2 re-execs into the venv, the interpreter that starts the chain does not
matter — it only has to be some Python 3.10+. The documentation fix is therefore **one
line in a Platform section** ("on Windows, `py -3` for `python3`"), not 211 edited command
examples. The only hard-coded call site that must change is
[md2pptx.js:661](../../skills/pptx/scripts/md2pptx.js#L661), which spawns the literal
string `python3` and has no bootstrap to save it.

## Blockers

### Tier A — blocks everything (install / import / invocation)

| # | Blocker | Anchor | Blast radius |
|---|---------|--------|--------------|
| A1 | `install.sh` is bash-only (`set -euo pipefail`, `command -v`, POSIX paths). No `install.ps1` / `install.cmd`. It is the documented mandatory bootstrap. | [install.sh:1](../../skills/docx/scripts/install.sh#L1), and 4 siblings | all 5 skills, 100% |
| A2 | `_venv_bootstrap.reexec_into_venv` probes and execs `.venv/bin/python`; on Windows the interpreter is `.venv\Scripts\python.exe`. The re-exec never fires, so every CLI runs under the ambient interpreter and dies with `ModuleNotFoundError` — or prints the `run: bash …/install.sh` hint, which is itself unrunnable. | [_venv_bootstrap.py:60](../../skills/docx/scripts/_venv_bootstrap.py#L60), [:84](../../skills/docx/scripts/_venv_bootstrap.py#L84) | 28 production modules across 5 skills |
| A3 | `import fcntl` at module top level in `_soffice.py` (used only for the shim build lock). `fcntl` does not exist on Windows → `ImportError` at import, before any LibreOffice call. | [_soffice.py:24](../../skills/docx/scripts/_soffice.py#L24) | `docx_accept_changes.py:51`, `xlsx_recalc.py:52`, `pptx_to_pdf.py:21`, `pptx_thumbnails.py:31` (+ the lazy import in `pptx2md/images.py:84`) |
| A4 | Every documented invocation is `python3 scripts/X.py`. `python3` is not a command on Windows (`py -3` / `python`; the Store alias is a stub). Occurs on 44 / 57 / 36 / 57 / 17 lines of the docx / xlsx / pptx / pdf / html `SKILL.md`. One JS call site spawns the literal string. | [md2pptx.js:661](../../skills/pptx/scripts/md2pptx.js#L661) and the five `SKILL.md` files | all 5 skills |

### Tier B — breaks specific features (import succeeds, feature does not)

| # | Blocker | Anchor |
|---|---------|--------|
| B1 | LibreOffice discovery has no Windows candidate (`C:\Program Files\LibreOffice\program\soffice.exe`). `shutil.which("soffice")` fails because the Windows installer does not put `program\` on `PATH`. The list is duplicated in three places, two of them replicated files. | [_soffice.py:41-48](../../skills/docx/scripts/_soffice.py#L41-L48), [preview.py:53-58](../../skills/docx/scripts/preview.py#L53-L58), [docx2md/_probes.js:9-13](../../skills/docx/scripts/docx2md/_probes.js#L9-L13) |
| B2 | `resolveMmdc()` shells out to `command -v mmdc` — a POSIX shell builtin, absent from `cmd.exe`. The local-bin branch resolves the extensionless `node_modules/.bin/mmdc` shim, which `spawnSync` cannot execute on Windows (`mmdc.cmd` is the executable one). Mermaid silently degrades to code blocks. | [md2pptx.js:60](../../skills/pptx/scripts/md2pptx.js#L60), [:56](../../skills/pptx/scripts/md2pptx.js#L56) |
| B3 | The AF_UNIX shim is structurally non-portable: `LD_PRELOAD` / `DYLD_INSERT_LIBRARIES`, a C source compiled by `build.sh`, and an `fcntl.flock` build lock. `_shim_library_path()` already returns `None` for non-Linux/Darwin — the code path is correct, the surrounding module is not (see A3). | [_soffice.py:104-112](../../skills/docx/scripts/_soffice.py#L104-L112), `office/shim/` |
| B4 | weasyprint (the default `pdf` render engine) needs a GTK3 / Pango / Cairo runtime that Windows does not ship. `install.sh` prints remediation for macOS, Debian and Fedora only. | [pdf/scripts/install.sh:94-106](../../skills/pdf/scripts/install.sh#L94-L106) |
| B5 | Poppler (`pdftoppm`, `pdftotext`) has no Windows package manager path; it backs `preview.py` for all four office skills and the high-fidelity shape route in `docx2md`. Same for `tesseract` / `ghostscript` (OCR in `pdf` and `pptx`) — remediation strings name only `brew` and `apt`. | [preview.py:110-116](../../skills/docx/scripts/preview.py#L110-L116), [pdf/scripts/install.sh:179-180](../../skills/pdf/scripts/install.sh#L179-L180) |
| B6 | `subprocess.run(..., text=True)` without `encoding=` (30 call sites in production code) decodes child output with the Windows ANSI codepage (cp1251 on a Russian host). Non-ASCII `soffice` / `pdftotext` diagnostics raise `UnicodeDecodeError` or mojibake instead of the intended error message. | e.g. [_soffice.py:255-261](../../skills/docx/scripts/_soffice.py#L255-L261) |

### Tier C — no way to prove Windows works

| # | Blocker | Anchor |
|---|---------|--------|
| C1 | The E2E harness is `tests/test_e2e.sh` × 5 (bash), and the CI matrix is `runs-on: ubuntu-22.04` only. There is no runner on which a Windows claim could be verified, and the `diff -q` replication gate lives inside those bash scripts. | [.github/workflows/office-skills.yml:32](../../.github/workflows/office-skills.yml#L32) |
| C2 | Test code uses `os.symlink` (needs Developer Mode or elevation on Windows), the `resource` module (POSIX-only), `#!/bin/sh` stub executables, and `os.chmod` with POSIX permission bits. | `xlsx2md/tests/test_cli_envelopes.py:120`, `tests/test_xlsx_check_rules.py:2479`, `tests/test_md2docx_mermaid_hygiene.py:41` |

## Two Windows traps that a naive port walks into

Neither is visible from the source on a POSIX host; both must be confirmed on a real
Windows box in the first hour of Stage 1, before any other Stage 1 work is scheduled.
They are recorded here because each one makes a port *appear* to work and then fail
downstream.

### T1 — `os.execv` does not replace the process on Windows

[_venv_bootstrap.py:89](../../skills/docx/scripts/_venv_bootstrap.py#L89) re-execs into
the venv with `os.execv`. On POSIX that replaces the process image: the shell keeps one
process handle, `sys.argv` and the eventual exit code survive intact — which is exactly
the contract the module's docstring promises.

Windows has no `execve`. CPython implements `os.exec*` over the CRT `_wexec*` family,
which **spawns a new process and terminates the caller**. Consequences for a console
invocation: the shell sees the first process exit and may return to the prompt while the
child is still writing the output file, and the child's exit code does not propagate to
whatever launched the CLI. For an agent that gates the next step on the exit code — which
is the whole invocation model of these skills — that is a silent-success failure mode.

Fix: branch in `reexec_into_venv`. POSIX keeps `os.execv`; on `nt` use
`subprocess.run([venv_py, *sys.argv])` followed by `sys.exit(proc.returncode)`. Costs one
extra process for the lifetime of the call and preserves both the exit code and the
shell's process handle. The existing `_REEXEC_FLAG` loop guard stays as-is — it is
transport-independent.

### T2 — `soffice.exe` returns before the conversion finishes

`soffice.exe` on Windows is a GUI-subsystem launcher: it starts `soffice.bin` and returns
immediately, without waiting and without a meaningful exit code. The console-subsystem
sibling `soffice.com`, in the same `program\` directory, blocks until the conversion is
done and propagates the real exit status. A Windows port that adds `soffice.exe` to the
candidate list in B1 gets `subprocess.run(..., check=True)` returning 0 against a file
that does not exist yet.

Fix: prefer `soffice.com` over `soffice.exe` on `nt` in all three discovery sites (B1).

**This is contained today, and that containment must not be refactored away.** Every
`soffice` call site already verifies the artifact rather than trusting the exit code:
`convert_to` re-checks `produced.is_file()`
([_soffice.py:314-316](../../skills/docx/scripts/_soffice.py#L314-L316)) and
`accept_changes` calls `verify_no_tracked_changes(output_path)` and unlinks the output on
any failure ([docx_accept_changes.py:178-184](../../skills/docx/scripts/docx_accept_changes.py#L178-L184)).
So T2 surfaces as a legible-but-misleading `Expected output not found` rather than a
corrupt document — the same discipline the LibreOffice 26.2 recalc work established.
The message needs to name the `.exe` / `.com` cause; the check itself is already right.

## Already Windows-safe — do not redo

Verified during the audit; these need no work and should not be "fixed":

- **The OOXML core** (`office/pack.py`, `unpack.py`, `validate.py`) normalises archive
  member paths with `Path.as_posix()` ([pack.py:98](../../skills/docx/scripts/office/pack.py#L98),
  [:136](../../skills/docx/scripts/office/pack.py#L136)) and otherwise uses `zipfile` +
  `lxml`. Pure-OOXML manipulation is portable today.
- **File I/O encoding hygiene** is disciplined: a sweep for `open()` / `read_text()` /
  `write_text()` without `encoding=` in production code returned only the shim build
  lock, which writes nothing. (The gap is in `subprocess`, not file I/O — see B6.)
- **`xlsx_check_rules/cli.py`** already branches on `hasattr(signal, "SIGALRM")` with a
  `threading.Timer` fallback documented as the Windows path
  ([cli.py:265-285](../../skills/xlsx/scripts/xlsx_check_rules/cli.py#L265-L285)).
- **`pdf/html2pdf_lib/render.py`** guards its watchdog the same way and states the
  limitation in the docstring ([render.py:113](../../skills/pdf/scripts/html2pdf_lib/render.py#L113)).
- **The docx JS layer** is largely Windows-aware already: `npx.cmd`, `where` instead of
  `which`, `file:///` drive-letter URLs, win32 Chrome locations
  ([_html2docx_svg_render.js:66](../../skills/docx/scripts/_html2docx_svg_render.js#L66),
  [:98](../../skills/docx/scripts/_html2docx_svg_render.js#L98),
  [:268](../../skills/docx/scripts/_html2docx_svg_render.js#L268),
  [_html2docx_walker.js:679](../../skills/docx/scripts/_html2docx_walker.js#L679)).

The pattern to copy is B3 / `xlsx_check_rules` / `render.py`: **branch and degrade with a
named limitation**, not emulate.

## Scope

Three stages. Stage 0 is independently shippable and is recommended regardless of whether
Stages 1-2 are ever funded — it converts an undocumented crash into a documented,
legible refusal.

### Stage 0 — honest scope (S)

Declare the supported platforms and fail legibly off them. No behaviour change on
macOS/Linux.

1. A "Supported platforms" section in `README.md` and in each office `SKILL.md`:
   macOS + Linux supported; **Windows via WSL2**, with the two-line WSL2 recipe; native
   Windows unsupported.
2. `_venv_bootstrap.reexec_into_venv` detects `os.name == "nt"` with no
   `.venv\Scripts\python.exe` and emits a one-line WSL2 pointer instead of the
   unrunnable `run: bash …/install.sh` hint.
3. `_soffice.py` moves `import fcntl` behind the Linux/Darwin branch it already has, so
   the module imports on Windows and fails at the `find_soffice()` call with the existing
   `SofficeError` message rather than at import.
4. A regression test locking (2) and (3), per the honest-scope precedent
   (`TestShimCrossProcessIPCLimitation`).

### Stage 1 — native Windows core (M-L)

Everything that needs no non-portable native runtime: OOXML manipulation, validation,
templates, password protection, Markdown↔OOXML conversion, `html` — the 39 entrypoints
counted above.

1. `install.ps1` at parity with `install.sh` (venv, `pip install -r`, `npm install`,
   host-tool probe with Windows remediation strings, smoke test, idempotent). Replicated
   to all five skills under the §2 protocol.
2. `_venv_bootstrap`: resolve `Scripts\python.exe` on `nt`, `bin/python` elsewhere, and
   apply the T1 transport branch.
3. `_soffice.py` + `preview.py` + `docx2md/_probes.js`: add the Windows LibreOffice
   locations with `soffice.com` preferred (T2), and honour a `SOFFICE_BIN` / `LO_BIN`
   override so a non-standard install is reachable without a code change.
4. Interpreter resolution: one Platform line per `SKILL.md` (see "What this changes about
   A4"), and `md2pptx.js:661` resolves the interpreter instead of hardcoding `python3`.
5. `md2pptx.js resolveMmdc()`: `mmdc.cmd` on win32, `where` instead of `command -v`.
6. `subprocess` decoding: `encoding="utf-8", errors="replace"` on the 30 `text=True`
   sites, so a cp1251 host cannot turn a diagnostic into a traceback.
7. **Out of scope for Stage 1, stated explicitly in the docs:** the AF_UNIX shim (B3) —
   Windows does not have the sandbox class it exists for.

### Stage 2 — full parity (L, optional)

Windows install paths and probes for the native-runtime features: weasyprint's GTK3
runtime (B4), Poppler, Tesseract, Ghostscript (B5). Each feature that cannot be made to
work gets a named limitation and a documented degradation, not a silent one.

## Acceptance criteria

- **Stage 0**: on a Windows host, `python scripts/preview.py --help` prints the WSL2
  pointer and exits non-zero; `import _soffice` succeeds; the four Tier-A3 CLIs reach
  argument parsing. Zero behaviour change on macOS/Linux, proven by the existing five
  E2E suites.
- **Stage 1**: `windows-latest` joins the CI matrix with a Windows-subset E2E suite
  (`test_e2e.ps1`, carrying the same `diff -q` replication gate as C1). Green on:
  md→docx/pptx, docx/xlsx/pptx→md, `office.validate`, `office_passwd`, template fill,
  `html` offline route.
- **Stage 2**: `preview.py`, `md2pdf.py`, `html2pdf.py`, and the OCR routes green on
  `windows-latest`, or each carries a limitation docstring plus a regression test.

## Constraints

Four of the files that must change are **replicated**, and the §2 protocol governs every
edit. Edit the docx copy only, then replicate in the same commit:

- `_soffice.py` — docx → xlsx, pptx (3 skills)
- `_errors.py`, `preview.py` — docx → xlsx, pptx, pdf (4 skills)
- `_venv_bootstrap.py` — docx → xlsx, pptx, pdf, html (5 skills)
- `install.sh` / `install.ps1` — per-skill, NOT replicated (each has its own dependency
  set), but they must stay structurally parallel

`diff -qr` must be clean for the replicated set before commit, and
`validate_skill.py` must exit 0 for all five skills.

## Open question for the owner

Stage 1 assumes native Windows is worth supporting at all. The cheaper answer is Stage 0
alone plus "use WSL2" — WSL2 already gives full parity today, including the shim, GTK,
Poppler and Tesseract, at the cost of one install. Stage 1+2 buys native `cmd.exe` /
PowerShell operation and a second CI lane to maintain in perpetuity. Decide before Stage
1 starts; Stage 0 is correct either way.
