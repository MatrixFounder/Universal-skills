# transcript-fetcher — skill improvement spec

**Status:** proposed
**Owner:** (unassigned)
**Origin:** import of the cyber•Fund *"Building AI-Native Startups [004]"* X‑Broadcast (2026‑07‑09). The
standard `transcript-fetcher` path could **not** produce the transcript for a ~70‑min X Broadcast — the
media download timed out — which forced a manual, out‑of‑skill workaround (parallel `yt-dlp` +
`mw transcribe`). This spec turns that workaround into first‑class skill behaviour and closes the
dependency‑discoverability gap that sent the operator down a false "yt‑dlp is missing" path.

All line references are to `skills/transcript-fetcher/scripts/` as of this writing.

---

## Summary of changes

| ID | Problem | Change | Priority |
|----|---------|--------|----------|
| **S1** | HLS broadcast/space downloads are **serial** → time out on long media | Add `--concurrent-fragments N` to the media download argv | **P0** |
| **S2** | Per‑attempt download timeout is a flat 180 s, not media‑aware | Make the media‑download timeout duration/size‑aware (or raise + document) | **P1** |
| **S3** | `yt-dlp` lives in the skill `.venv`; a naïve `which yt-dlp` gives a **false negative** → risk of duplicate global install | Add a `doctor`/`--check` entrypoint + a prominent SKILL.md "deps are vendored" note | **P0** |
| **S4** | Timeout surfaces as an opaque `TranscriptFetchError` | Classify as retryable + actionable remediation in the message | **P2** |
| **S5** | ASR path is macOS/MacWhisper‑bound; portability is implicit | Document the backend chain + the exit‑7 failure mode prominently | **P2** |
| **S6** | X Broadcast/Space auth relies on `~/.transcript-fetcher/x-cookies.txt` (silently) | Document the cookie contract + a clear auth‑failure remediation | **P2** |

---

## S1 — Parallelise HLS fragment download (P0, the real blocker)

### Problem
An X Broadcast is an HLS stream of **many small fragments** (this import: **2089 fragments** for a
69.6‑min broadcast). `download_audio()` builds a yt‑dlp argv with **no** `--concurrent-fragments`, so
fragments download **one at a time**.

**Measured:** serial ≈ **120 KB/s** (26 MB after ~4 min) → hit the per‑attempt `timeout` (600 s in the
call that failed) with the media incomplete → `download_audio()` returns
`"timeout downloading audio (>600s)"` and **no `_raw` is written**. The same media downloaded with
`yt-dlp -N 16` reached **2.2 MB/s (130 MB in ~2 min)** — an ≈**18×** speedup. Parallelism, not a bigger
timeout, is the fix.

### Location
`scripts/sources/_ytdlp_media.py`, `download_audio()` (defined ~L344). Format/extract args are built at:
- L380 `args += ["-f", "worstaudio/worst[acodec!=none]/worst"]`
- L385 `args += ["-x", "--audio-format", "m4a"]` (ffmpeg present)
- L389–390 `--download-sections *0-<N*60>` (only when `--max-duration-min` is set)
- L398–399 `subprocess.run(args, …, timeout=timeout_sec)`

### Proposed change
Add concurrent‑fragment downloading to the media argv (HLS is fragmented; this is safe for progressive
too — yt‑dlp ignores it when there is a single file):

```python
# _ytdlp_media.py, download_audio(), alongside the -f/-x args
concurrency = concurrent_fragments if concurrent_fragments and concurrent_fragments > 0 else DEFAULT_CONCURRENT_FRAGMENTS
args += ["--concurrent-fragments", str(concurrency)]
```

- `DEFAULT_CONCURRENT_FRAGMENTS` = **8** (config‑overridable; see below). 8–16 is the sweet spot; keep it
  bounded to avoid rate‑limit trips.
- Wire a new knob end‑to‑end:
  - `_config.py` — read `TRANSCRIPT_FETCHER_CONCURRENT_FRAGMENTS` (env / `.env`), default 8.
  - `fetch.py` — add `--concurrent-fragments N` (forwarded to `download_audio`), default from config.
- Apply the **same** flag to the caption/subtitle download paths only if they ever become fragmented
  (they are single files today — no change needed there).

### Acceptance criteria
- A ≥60‑min X Broadcast transcribes end‑to‑end via the standard `fetch.py <url>` with **default** flags
  (no manual `-N`), inside the default timeout.
- Offline/unit: the constructed argv for an HLS source contains `--concurrent-fragments` with the
  configured value; a `--concurrent-fragments 1` override reproduces serial behaviour.

---

## S2 — Media‑download timeout should be media‑aware (P1)

### Problem
`--timeout-sec` (default **180 s**, per `fetch.py` help) is a **per‑attempt** wall‑clock that gates BOTH
the fast metadata probe and the potentially‑large media download. For a long broadcast the same 180 s
is wildly too small for the download even after S1 (a 130 MB pull over a slow link can exceed it), while
being fine for the probe. The failing run only survived because the caller passed 600 s by hand.

### Proposed change
- Give the **media download** its own, larger budget, separate from the metadata‑probe timeout. Options
  (pick one, in order of preference):
  1. Derive a floor from the probed duration when available: `download_timeout = max(base, duration_s * K)`
     (e.g. `K≈4`, `base=600`). Duration is often `NA` for X (this import), so treat `NA` as "use a
     generous default", e.g. **1800 s**.
  2. Simpler: introduce `--media-timeout-sec` (default 1800) distinct from `--timeout-sec` (probe, 180).
- Keep S1's parallelism as the primary mitigation; S2 is the safety margin.

### Acceptance criteria
- With default flags, a broadcast whose duration probes as `NA` does not fail on a too‑small default
  media timeout.
- The metadata probe still uses the small (≤60 s socket / 180 s attempt) budget.

---

## S3 — Dependency discoverability: `yt-dlp` is vendored, not on PATH (P0)

### Problem
`yt-dlp` is a **Python module** installed into `scripts/.venv` by `install.sh` (`requirements.txt`:
`yt-dlp>=2026.3.17`). It is invoked as `python -m yt_dlp` **under the venv interpreter**. Therefore:
- `which yt-dlp` on `$PATH` returns **nothing** → a caller (human or a weaker model) concludes "yt‑dlp is
  missing" and may `pip install` / `brew install` a **duplicate**, or abort. This is exactly what
  happened during the 004 import (a self‑inflicted false alarm, but the skill offered no signal to
  prevent it).
- `install_components.py::_have_yt_dlp()` proves availability **only** by `import yt_dlp` — which itself
  must run under the venv python. There is no cheap, surface‑level probe a caller would naturally reach
  for.

### Proposed change
1. **`fetch.py doctor` (or `--check`)** — a zero‑arg entrypoint that prints, as JSON and human text, the
   resolved interpreter + the status of every dependency (yt‑dlp version, ffmpeg, each ASR backend) and
   the exact remediation for any gap. This is the one command a caller/skill‑runner should invoke to
   answer "is this skill ready?" — never `which yt-dlp`.
2. **SKILL.md** — add a prominent **Dependencies** block near the top:
   > `yt-dlp` is **vendored in `scripts/.venv`** (installed by `scripts/install.sh`). Do **NOT**
   > `which yt-dlp` / `pip install` / `brew install` it globally — check with
   > `scripts/.venv/bin/python -m yt_dlp --version` or `python scripts/fetch.py doctor`. Callers that
   > shell in MUST use the venv interpreter (`scripts/.venv/bin/python scripts/fetch.py …`).
3. **Consistency for downstream callers** — document that integrators (e.g. obsidian‑llm‑wiki
   `_transcript_python()`) already resolve the venv interpreter; the doctor output should be the
   canonical readiness check they can call too.

### Acceptance criteria
- `python scripts/fetch.py doctor` exits 0 and reports yt‑dlp present when the venv is bootstrapped, and
  exits non‑zero with actionable remediation when it is not — **without** relying on `$PATH`.
- SKILL.md explicitly warns against global install and names the venv probe.

---

## S4 — Classify the download timeout as retryable + actionable (P2)

### Problem
The failure reaches the caller as a generic `TranscriptFetchError` (`code 3`) with message
`timeout downloading audio (>600s)`. Nothing tells the operator that the remedy is *parallelism / a
larger media timeout*, not "the video has no transcript".

### Proposed change
- In `classify_failure()` / the `download_audio` timeout branch, tag audio‑download timeouts as
  **transient/retryable** and, after S1/S2, optionally auto‑retry once with a larger budget.
- Enrich the error `details` with a remediation string: *"increase `--media-timeout-sec` and/or
  `--concurrent-fragments`; long HLS broadcasts need parallel fragment download"*.

### Acceptance criteria
- A simulated download timeout produces an error whose remediation names concurrency + media timeout.

---

## S5 — Document ASR portability & the exit‑7 failure mode (P2)

### Problem
The 004 transcript was produced by **MacWhisper** (`mw`, Large v3 Turbo) — macOS + a paid app. The
backend chain is `mw → Whisper CLI → whisper.cpp → (opt‑in) cloud`; if **none** is present a caption‑less
broadcast fails with `MissingDependencyError` (exit **7**). This is correct behaviour but under‑advertised:
the same import on a Linux/CI box with no ASR backend fails hard.

### Proposed change
- SKILL.md: a short **ASR portability** note — the backend chain, that caption‑less
  Broadcasts/Spaces **require** ffmpeg + one ASR backend, and the exit‑7 remediation
  (`install_components.py --install-whisper`, or `--asr-allow-cloud`).
- `doctor` (S3) reports which ASR backends are resolvable so the gap is visible **before** a long fetch.

---

## S6 — Make the X cookie contract explicit (P2)

### Problem
The broadcast media download silently used `~/.transcript-fetcher/x-cookies.txt`. X Broadcasts/Spaces are
frequently auth‑gated; when the cookie expires, future imports fail (auth / rate‑limit) with no obvious
pointer to the fix.

### Proposed change
- Document the cookie file location + format (Netscape `cookies.txt`) and `--cookies-from-browser` /
  `--cookies-file` overrides in SKILL.md under X sources.
- On an auth/403 download failure, emit a remediation naming the cookie refresh path.

---

## Test plan

- **Unit (offline):** argv builders assert `--concurrent-fragments` presence/value (S1) and the
  media‑vs‑probe timeout split (S2); `doctor` JSON shape (S3); error remediation strings (S4/S6).
- **Integration (network, opt‑in):** a real ≥60‑min X Broadcast transcribes end‑to‑end with default
  flags (S1+S2). Gate behind an env flag so CI without cookies/ASR skips it.
- **Regression:** YouTube/Vimeo caption paths unchanged; a progressive (non‑HLS) source still downloads
  (concurrent‑fragments is a no‑op there).

## Risks / notes
- Higher fragment concurrency can trip host rate limits → keep the default modest (8) and bounded.
- `--download-sections` clipping (S2 option) needs ffmpeg (already required on the HLS path).
- S3's `doctor` must not import heavy modules eagerly (keep the readiness probe cheap).
