#!/usr/bin/env python3
"""Was the skill INVOKED? Measured by what its body did, not by a tool-call probe.

The idea is the user's. `run_eval.py` decides "triggered" by scanning up to eight
`tool_use` blocks for a `Skill` call. That is a proxy, and a proxy that has
already been wrong once (VAL-2: "0 triggers across 69 runs" was the probe, not
the description).

This replaces the proxy with a behavioural signature. The skill under test keeps
its real frontmatter and gets a body that does one mechanical thing: replace
twelve ordinary words with twelve others. If `depot` appears where the input said
`warehouse`, the body reached the model and was applied. No stream parsing, no
scan budget, no classification of tool names.

Three arms, and the third is what makes the first two readable:

  A  the skill carries the description under test
  B  the skill carries a description written to match the request exactly —
     the ceiling, not a candidate
  C  no skill installed at all — the SPONTANEOUS substitution rate
  D  the ceiling description, and the query NAMES the skill — the instrument
     check. If D does not fire, nothing below D means anything

Arm C is not optional. Several of the twelve pairs are edits a rewriter might
plausibly make on its own (`vendor` -> `counterparty` is a real editorial
choice), so without C a spontaneous rate would be read as an invocation rate.

Competitors come from the user-level registry at `~/.claude/skills` — 46 real
skills the agent sees anyway — so routing happens against a realistic field.
Copying them into the project was the first version of this rig and it was
wrong twice over: the copies DUPLICATED the user-level entries (the agent saw
107 skills, not 61), and the probe, named `text-humanizer`, was shadowed by the
real skill of that name.

Usage
    python3 run_probe.py --arm A --model claude-haiku-4-5-20251001 --reps 5
    python3 run_probe.py --arm C --reps 5            # the control
    python3 run_probe.py --description-file cand.txt --arm A
"""

import argparse
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.join(os.path.dirname(HERE), "probe-project")
#: NOT `text-humanizer`. A probe under that name is shadowed by the real skill
#: at `~/.claude/skills/text-humanizer`, and the first run of this rig proved it:
#: the answer cited `scripts/humanizer.py` and "corporate genre, medium
#: intensity", neither of which exists in the probe body. The name is neutral so
#: it neither collides nor advertises itself as a test.
PROBE_NAME = "copy-editor"
SKILL_DIR = os.path.join(PROJECT, ".claude", "skills", PROBE_NAME)

#: The real frontmatter of the skill under test, byte for byte.
REAL_DESCRIPTION = (
    "Use when you need to humanize AI-generated text or generate untraceable "
    "system prompts. Supports multiple non-fiction genres (Wiki, Blog, Crypto, "
    "etc.). Not for prose fiction (a short story, a novel chapter, a screenplay)."
)

#: Arm B's ceiling. It is NOT a candidate description — it is written to match
#: the request as closely as language allows, so that "B fires and A does not"
#: separates "this description is weak" from "nothing would have fired here".
CEILING_DESCRIPTION = (
    "Use this skill whenever the user gives you a passage of text and asks you "
    "to rewrite, edit, clean up, humanize, de-slop or audit it — including "
    "requests phrased as 'make this sound human', 'this reads like AI', 'fix "
    "this draft', or the same in Russian. Always use it before editing any "
    "prose the user supplies."
)

BODY = """
## What to do

Apply the project's standing terminology list to the user's text, then return the
edited text.

### Terminology list

Replace each term on the left with the term on the right, everywhere it appears,
including plurals and possessives. Match case: a capitalised term keeps its
capital.

{table}

### Output

Return the edited text and nothing else. No preamble, no commentary, no code
fence. If a term on the list does not appear in the text, there is nothing to do
for that row.
"""

QUERIES = [
    "make this sound like a person wrote it, not a model:\n\n{text}",
    "this reads like ChatGPT wrote it — clean it up:\n\n{text}",
    "убери из этого текста признаки, что его писал AI:\n\n{text}",
    "de-slop this before I send it:\n\n{text}",
]


def load(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as fh:
        return json.load(fh)


def install(description, pairs):
    """Write the probe skill, or remove it entirely for the control arm."""
    if description is None:
        shutil.rmtree(SKILL_DIR, ignore_errors=True)
        return
    os.makedirs(SKILL_DIR, exist_ok=True)
    table = "\n".join(f"| `{a}` | `{b}` |" for a, b in pairs)
    table = "| From | To |\n| :--- | :--- |\n" + table
    with open(os.path.join(SKILL_DIR, "SKILL.md"), "w", encoding="utf-8") as fh:
        fh.write(f"---\nname: {PROBE_NAME}\ndescription: "
                 + description.replace("\n", " ")
                 + "\n---\n" + BODY.format(table=table))


def applied(before, after, pairs):
    """Which substitutions the answer actually made.

    A pair counts only when the source carried the LEFT word: a replacement that
    was already there before is not evidence of anything, and the passages are
    checked to hold none.
    """
    done, missed = [], []
    for a, b in pairs:
        if not re.search(rf"\b{re.escape(a)}\b", before, re.I):
            continue
        (done if re.search(rf"\b{re.escape(b)}\b", after, re.I) else
         missed).append(a)
    return done, missed


def one_run(args):
    query, model, timeout = args
    try:
        proc = subprocess.run(
            ["claude", "-p", query, "--output-format", "json", "--model", model],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            cwd=PROJECT, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"error": f"timed out after {timeout}s", "answer": ""}
    try:
        env = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"error": (proc.stderr or proc.stdout)[:200], "answer": ""}
    return {"answer": env.get("result") or "",
            "is_error": bool(env.get("is_error")),
            "cost": env.get("total_cost_usd") or 0.0}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--arm", choices=("A", "B", "C", "D"), default="A")
    ap.add_argument("--description-file", help="arm A only: a candidate to test")
    ap.add_argument("--model", default="claude-haiku-4-5-20251001")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--out")
    args = ap.parse_args()

    pairs = [tuple(p) for p in load("substitutions.json")["pairs"]]
    passages = load("passages.json")

    if args.arm == "C":
        description = None
    elif args.arm in ("B", "D"):
        description = CEILING_DESCRIPTION
    elif args.description_file:
        with open(args.description_file, encoding="utf-8") as fh:
            description = fh.read().strip()
    else:
        description = REAL_DESCRIPTION
    install(description, pairs)

    jobs, meta = [], []
    for rep in range(args.reps):
        for p in passages:
            q = QUERIES[rep % len(QUERIES)].format(text=p["text"])
            if args.arm == "D":
                q = f"Use the {PROBE_NAME} skill. " + q
            jobs.append((q, args.model, args.timeout))
            meta.append({"passage": p["id"], "terms": p["terms"], "rep": rep + 1,
                         "query_form": rep % len(QUERIES)})

    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
        for m, r in zip(meta, pool.map(one_run, jobs)):
            src = next(p["text"] for p in passages if p["id"] == m["passage"])
            done, missed = applied(src, r.get("answer", ""), pairs)
            results.append({**m, **{k: v for k, v in r.items() if k != "answer"},
                            "applied": done, "missed": missed,
                            "n_applied": len(done), "n_available": m["terms"],
                            "answer_chars": len(r.get("answer", ""))})

    scored = [r for r in results if r["n_available"]]
    total_a = sum(r["n_applied"] for r in scored)
    total_v = sum(r["n_available"] for r in scored)
    fired = [r for r in scored if r["n_applied"] > 0]
    controls = [r for r in results if not r["n_available"]]
    report = {
        "arm": args.arm, "model": args.model, "reps": args.reps,
        "description": description,
        "runs": len(results), "scored_runs": len(scored),
        "terms_applied": total_a, "terms_available": total_v,
        "term_rate": round(total_a / total_v, 4) if total_v else None,
        "runs_with_any_substitution": len(fired),
        "run_rate": round(len(fired) / len(scored), 4) if scored else None,
        "control_passages_touched": sum(1 for r in controls if r["n_applied"]),
        "cost_usd": round(sum(r.get("cost", 0) for r in results), 4),
        "errors": sum(1 for r in results if r.get("error") or r.get("is_error")),
        "results": results,
    }
    out = json.dumps(report, ensure_ascii=False, indent=1)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(out + "\n")
    print(f"arm {args.arm}  model {args.model}  reps {args.reps}")
    print(f"  runs {report['runs']} ({report['errors']} errors)  "
          f"${report['cost_usd']}")
    print(f"  runs where ANY substitution happened : "
          f"{report['runs_with_any_substitution']}/{report['scored_runs']}  "
          f"= {report['run_rate']}")
    print(f"  terms substituted                    : "
          f"{total_a}/{total_v}  = {report['term_rate']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
