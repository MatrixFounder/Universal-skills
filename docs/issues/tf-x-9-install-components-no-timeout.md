---
id: TF-X-9
type: known-issue
status: open
opened_at: 2026-08-19
category: robustness
severity: LOW
component: transcript-fetcher
slug: tf-x-9-install-components-no-timeout
---

# TF-X-9 — `install_components.py` runs `pip` / `brew` / `apt` with no timeout (unbounded hang)

> Found by the completeness sweep run while fixing
> [TF-X-8](tf-x-8-asr-subprocess-timeout-no-process-group.md) (2026-08-19). Filed separately
> because it is a DIFFERENT defect class from TF-X-7/TF-X-8, not a missed instance of theirs.

**Status:** open • **Severity:** LOW •
**Location:** `scripts/install_components.py:177` (`_install_whisper` —
`sys.executable -m pip install -U openai-whisper`) and `scripts/install_components.py:201`
(`_system_install` — `shlex.split` of `brew install …` / `apt install …`).

**Symptom:** both call `subprocess.run(...)` with **no `timeout=`**. A wedged package index,
a hung TLS handshake, or a `brew`/`apt` lock held by another process makes the skill's
`--install-*` path hang indefinitely with no ceiling and no diagnostic.

**Why this is NOT TF-X-7/TF-X-8:** those are *orphan* defects — a `TimeoutExpired` that
reaches only the direct child. Here there is no timeout at all, so there is no
`TimeoutExpired` path and no orphan. And because these sites do not set `start_new_session`,
they stay in the CLI's foreground process group, so **Ctrl-C correctly reaches the whole
tree** (pip's build backends, brew's downloads) — which is exactly the behaviour an
interactive installer wants. Routing them through `run_in_process_group` as-is would
therefore make Ctrl-C *worse*, not better, unless a timeout is chosen at the same time.

**Reproduction (not attempted):** point `pip` at an unreachable index (`PIP_INDEX_URL` to a
blackholed host) and run `--install-whisper`; the process hangs with no ceiling.

**Workaround:** Ctrl-C works and reaches the whole install tree. The documented alternative
is to run the install command by hand, which `fetch.py doctor` already prints for every
missing component.

**Fix path:** the real decision is what budget is defensible, not which helper to call — a
cold `pip install openai-whisper` pulls torch (hundreds of MB) and a `brew install` can
compile from source, so any ceiling short of tens of minutes will fire on a legitimately slow
link. Suggested shape: a generous default (e.g. 3600 s) overridable by an env knob, applied
via plain `subprocess.run(timeout=…)`. If it is ever moved onto `run_in_process_group`,
`start_new_session=True` must be paired with a deliberate answer for interactive Ctrl-C,
since these are the only sites in the skill a human watches in real time.

**Do-not:** do not fold this into TF-X-7 or TF-X-8 — mixing an unbounded-hang defect into an
orphan-teardown record blurs both, and the two want opposite process-group treatment. Do not
add a short timeout "to be safe": killing a half-finished `brew`/`pip` mid-transaction is
worse than the hang it prevents.
