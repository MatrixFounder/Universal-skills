#!/usr/bin/env python3
"""Executor for the text-humanizer eval set (spec R1).

Two arms per case, differing in ONE input. The `with_skill` arm is handed the
prompt `scripts/humanizer.py` assembles for that case's genre; the `baseline`
arm is handed nothing in its place. Same fixture, same instruction, same model,
same working directory shape, same tool denials.

Neither arm's instruction names a marker, a pattern or a rule. An instruction
that said "remove em dashes" would put the skill in both arms and measure
nothing.

This is the ONLY script here that spends tokens. `--dry-run` prints the command
and spawns nothing, which is how `selftest_evals.py` checks the command shape
for free.

Exit codes
  0  every requested run completed
  1  at least one run failed or returned an empty document
  2  the working directory is not isolated
  3  the invocation is wrong
"""

import argparse
import concurrent.futures
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
HUMANIZER = os.path.join(SKILL, "scripts", "humanizer.py")

ARMS = ("baseline", "with_skill")

#: Sonnet, not Opus. The eval measures what the SKILL adds, and a weaker
#: rewriter leaves more room for that difference to show. Pin it either way: a
#: model rollout must not read as a skill regression.
DEFAULT_MODEL = "claude-sonnet-5"

#: The rewrite needs no tool. Denying them removes the second path to the
#: skill's own reference files — under this repository the baseline arm could
#: otherwise read `references/patterns_universal.md` and become the other arm.
DENIED_TOOLS = ("Bash", "Read", "Write", "Edit", "MultiEdit", "NotebookEdit",
                "Glob", "Grep", "WebFetch", "WebSearch", "Task", "TodoWrite",
                "Skill")

#: A directory holding any of these teaches the baseline arm the skill that
#: defines the arm.
LEAK_NAMES = ("CLAUDE.md", ".agent", ".claude", "AGENTS.md", "GEMINI.md")

SKILL_HEADER = "=== BEGIN EDITING INSTRUCTIONS ===\n"
SKILL_FOOTER = "\n=== END EDITING INSTRUCTIONS ===\n\n"

#: Identical in both arms, byte for byte. TC-EV-08 asserts the arms differ by
#: the skill block alone, and TC-EV-09 asserts no task template names a marker,
#: a pattern number or a rule -- an instruction that said "remove em dashes"
#: would put the skill in the baseline arm and the case would measure nothing.
#:
#: A case may override this with a `task` field naming a file under `tasks/`.
#: That is how a PRESSURE case works (guide section 6.4): the pressure lives in
#: what the user asks for, and it reaches BOTH arms unchanged, so the one input
#: that differs between them is still only the skill block.
TASK = """Rewrite the text below so that it does not read as machine-written.

Every fact, figure, name and identifier in the source must survive the rewrite.
Do not add facts that are not in the source.

Return ONLY the rewritten text. No preamble, no commentary, no code fence.

=== BEGIN TEXT ===
{text}
=== END TEXT ===
"""

FENCE = re.compile(r"\A\s*```[^\n]*\n(.*?)\n?```\s*\Z", re.S)


class NotIsolated(RuntimeError):
    """The working directory would leak the skill into the baseline arm."""


class HumanizerFailed(RuntimeError):
    """`humanizer.py` did not produce a prompt. There is no with_skill arm."""


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def leaks_above(path):
    """Return every context file at or above *path*, stopping at $HOME.

    `~/.claude` is deliberately outside the walk: it is user-level
    configuration, loaded identically for both arms, and it does not hold this
    skill's reference files.
    """
    found = []
    home = os.path.realpath(os.path.expanduser("~"))
    cur = os.path.realpath(path)
    while cur != home:
        for name in LEAK_NAMES:
            candidate = os.path.join(cur, name)
            if os.path.exists(candidate):
                found.append(candidate)
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return found


def isolated_workdir(base=None):
    """Create a working directory and assert nothing above it leaks."""
    path = tempfile.mkdtemp(prefix="humanizer-eval-", dir=base)
    leaks = leaks_above(path)
    if leaks:
        shutil.rmtree(path, ignore_errors=True)
        raise NotIsolated("; ".join(leaks))
    return path


def assemble_skill_prompt(genre, mode="humanize", intensity="auto", style=None,
                          skill_root=None):
    """Return `humanizer.py`'s stdout for *genre*.

    The script is CALLED rather than reimplemented, so a genre's intensity, its
    pattern file and the template all reach this eval exactly as a user gets
    them. Its exit codes are documented as 0 on success and 2 on a usage error.

    `skill_root` points the call at a DIFFERENT copy of the skill -- an older
    checkout, say. That is what makes a version A/B possible: R2-R7 grew the
    assembled prompt by about 60% at every intensity, and whether that bought
    anything cannot be read off a campaign drawn entirely after the growth.
    """
    humanizer = (os.path.join(skill_root, "scripts", "humanizer.py")
                 if skill_root else HUMANIZER)
    if not os.path.isfile(humanizer):
        raise HumanizerFailed(f"no humanizer.py at {humanizer}")
    argv = [sys.executable, humanizer, "--genre", genre,
            "--mode", mode, "--intensity", intensity]
    if style:
        argv += ["--style", style]
    proc = subprocess.run(argv, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    if proc.returncode != 0 or not proc.stdout.strip():
        raise HumanizerFailed(
            f"exit {proc.returncode}: {proc.stderr.strip()[:400]}")
    return proc.stdout


def load_task(case):
    """Return the task template for *case*: its own, or the shared default."""
    rel = case.get("task")
    if not rel:
        return TASK
    text = _read(os.path.join(HERE, rel))
    if "{text}" not in text:
        raise ValueError(f"{rel}: a task template must carry the {{text}} slot")
    return text


def build_prompt(fixture_text, arm, skill_prompt=None, task_template=None):
    """Return the prompt for *arm*. The arms differ by the skill block only."""
    task = (task_template or TASK).format(text=fixture_text)
    if arm == "baseline":
        return task
    if arm != "with_skill":
        raise ValueError(f"unknown arm {arm!r}")
    if skill_prompt is None:
        raise ValueError("with_skill needs the assembled prompt")
    return SKILL_HEADER + skill_prompt + SKILL_FOOTER + task


def skill_block(skill_prompt):
    """Return the exact bytes `build_prompt` prepends for `with_skill`."""
    return SKILL_HEADER + skill_prompt + SKILL_FOOTER


def build_command(prompt, model):
    """Return the argv for one `claude -p` run."""
    return ["claude", "-p", prompt,
            "--output-format", "json",
            "--model", model,
            "--disallowed-tools", *DENIED_TOOLS]


#: 600 s was not enough for a pressure case: two of three P1 `with_skill` runs
#: in the 2026-09-03 campaign died at the limit, and a timeout is recorded as an
#: instrument failure rather than as a result, so it costs the draw. The
#: pressure briefs are long AND pose an explicit dilemma, which is exactly the
#: shape that takes the model longest.
DEFAULT_TIMEOUT = 900


def spawn(prompt, model, workdir, timeout=DEFAULT_TIMEOUT):
    """Run one agent and return its envelope. The only token-spending call."""
    env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
    try:
        proc = subprocess.run(build_command(prompt, model), cwd=workdir,
                              env=env, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=timeout)
    except subprocess.TimeoutExpired:
        # Recorded as a failed run rather than raised. One stalled case must
        # not discard the arms that already completed.
        return {"is_error": True, "result": "",
                "error": f"timed out after {timeout}s", "returncode": None}
    if proc.returncode != 0 and not proc.stdout.strip():
        return {"is_error": True, "result": "",
                "error": proc.stderr.strip()[:2000],
                "returncode": proc.returncode}
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return {"is_error": True, "result": "",
                "error": f"unparsable envelope: {exc}",
                "returncode": proc.returncode}


def unwrap(text):
    """Strip ONE enclosing fenced block. Returns (text, unwrapped).

    The task forbids a fence, so an unwrapped answer is worth recording: it is
    the instruction being ignored, not a grading concern.
    """
    m = FENCE.match(text or "")
    return (m.group(1), True) if m else (text or "", False)


def _write_meta(path, payload):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1)


def run_case(case, arm, rep, model, out_root, dry_run=False, skill_root=None):
    """Execute one arm of one case and write the corpus entry."""
    fixture_text = _read(os.path.join(HERE, case["fixture"]))
    skill_prompt = (assemble_skill_prompt(case["genre"], style=case.get("style"),
                                          skill_root=skill_root)
                    if arm == "with_skill" else None)
    task_template = load_task(case)
    prompt = build_prompt(fixture_text, arm, skill_prompt, task_template)
    if dry_run:
        print(f"[dry-run] {case['id']}/{arm}/rep-{rep}: "
              f"{' '.join(build_command('<prompt>', model))}"
              f"  (prompt {len(prompt)} chars)")
        return {"dry_run": True}

    workdir = isolated_workdir()
    try:
        env = spawn(prompt, model, workdir)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    body, unwrapped = unwrap(env.get("result", ""))
    arm_dir = os.path.join(out_root, case["id"], arm)
    os.makedirs(arm_dir, exist_ok=True)
    with open(os.path.join(arm_dir, f"rep-{rep}.md"), "w",
              encoding="utf-8") as fh:
        fh.write(body)
    _write_meta(os.path.join(arm_dir, f"rep-{rep}.meta.json"), {
        "case": case["id"], "arm": arm, "rep": rep, "model": model,
        "genre": case["genre"], "style": case.get("style"),
        "fixture_sha256_16": _sha(fixture_text),
        "task": case.get("task"),
        "task_sha256_16": _sha(task_template),
        "skill_prompt_sha256_16": _sha(skill_prompt) if skill_prompt else None,
        "skill_root": skill_root,
        "skill_applied": arm == "with_skill",
        "unwrapped_fence": unwrapped,
        "is_error": bool(env.get("is_error")),
        "error": env.get("error"),
        "permission_denials": env.get("permission_denials", []),
        "models_used": sorted(env.get("modelUsage", {})),
        "total_cost_usd": env.get("total_cost_usd"),
        "duration_ms": env.get("duration_ms"),
        "session_id": env.get("session_id"),
        "output_chars": len(body),
    })
    return {"ok": bool(body.strip()) and not env.get("is_error"),
            "chars": len(body), "cost": env.get("total_cost_usd") or 0.0}


def plan_runs(evals, reps=1, cases=None, arms=None):
    """Return every run this invocation will execute, before anything spawns."""
    wanted = set(cases or ())
    runs = []
    for case in evals["cases"]:
        if wanted and case["id"] not in wanted:
            continue
        # A case declares which arms it has. A `coverage` case has one: it asks
        # whether the skill behaves correctly on a genre, not whether it beats
        # no skill, and the `failure_mode` cases already answer the second.
        declared = case.get("arms") or list(ARMS)
        for arm in (arms or declared):
            if arm not in declared:
                continue
            for rep in range(1, reps + 1):
                runs.append((f"{case['id']}/{arm}/rep-{rep}", case, arm, rep))
    return runs


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Run the text-humanizer eval campaign "
                    "(this is the script that spends tokens)")
    ap.add_argument("--evals", default=os.path.join(HERE, "evals.json"))
    ap.add_argument("--out-root", default=os.path.join(HERE, "runs", "scratch-corpus"),
                    help="where to write this campaign. A real campaign passes\n"
                         "runs/<UTC date>-<label>-corpus: guide 7.2 wants a new\n"
                         "directory per version, not an overwritten one")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--skill-root", default=None, metavar="DIR",
                    help="assemble the with_skill prompt from THIS copy of the "
                         "skill instead of the working tree. A version A/B "
                         "needs it: a campaign drawn entirely after a change "
                         "cannot say what the change bought")
    ap.add_argument("--reps", type=int, default=1)
    # `nargs="+"` with `action="extend"` accepts BOTH `--cases E1 E2` and
    # `--cases E1 --cases E2`. With the previous `action="append"` the first
    # form -- the one anybody types -- raised "unrecognized arguments: E2",
    # which `exit_on_error = False` then swallowed into a silent exit 3.
    ap.add_argument("--cases", action="extend", nargs="+", dest="cases",
                    metavar="ID", help="run only these case ids")
    ap.add_argument("--arm", action="extend", nargs="+", dest="arms",
                    choices=ARMS, metavar="ARM",
                    help="run only these arms")
    ap.add_argument("--jobs", type=int, default=1,
                    help="concurrent agents; each run is an independent "
                         "process writing its own file")
    ap.add_argument("--dry-run", action="store_true",
                    help="print each command and spawn nothing")
    # `exit_on_error = False` is what keeps a usage error from killing the
    # process, but it also routes argparse's own message into the exception
    # instead of stderr. Print it: an exit 3 that says nothing sends the caller
    # to read the source to find out which flag was wrong.
    ap.exit_on_error = False
    try:
        args = ap.parse_args(argv)
    except argparse.ArgumentError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        ap.print_usage(sys.stderr)
        return 3
    except SystemExit as exc:
        code = getattr(exc, "code", 1)
        return 0 if code == 0 else 3

    if args.reps % 2 == 0:
        print("usage error: --reps must be odd; an even count lets an exact "
              "split decide by comparison order", file=sys.stderr)
        return 3
    if args.jobs < 1:
        print("usage error: --jobs must be at least 1", file=sys.stderr)
        return 3
    if not os.path.isfile(args.evals):
        print(f"usage error: no eval file at {args.evals}", file=sys.stderr)
        return 3

    with open(args.evals, encoding="utf-8") as fh:
        evals = json.load(fh)
    runs = plan_runs(evals, args.reps, args.cases, args.arms)
    failures, cost = [], 0.0

    def execute(entry):
        label, case, arm, rep = entry
        return label, run_case(case, arm, rep, args.model, args.out_root,
                               args.dry_run, args.skill_root)

    def record(label, res):
        nonlocal cost
        cost += res.get("cost", 0.0)
        if args.dry_run:
            return
        if not res.get("ok"):
            failures.append(label)
            print(f"  {label}: FAILED")
        else:
            print(f"  {label}: {res['chars']} chars")

    try:
        if args.jobs == 1 or args.dry_run:
            for entry in runs:
                record(*execute(entry))
        else:
            with concurrent.futures.ThreadPoolExecutor(args.jobs) as pool:
                for future in concurrent.futures.as_completed(
                        [pool.submit(execute, e) for e in runs]):
                    record(*future.result())
    except NotIsolated as exc:
        print(f"not isolated: {exc}", file=sys.stderr)
        return 2
    except HumanizerFailed as exc:
        print(f"humanizer.py failed: {exc}", file=sys.stderr)
        return 1

    if not args.dry_run:
        print(f"\n{len(runs)} runs   cost: ${cost:.2f}   "
              f"failures: {len(failures)}")
        for f in failures:
            print(f"  {f}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
