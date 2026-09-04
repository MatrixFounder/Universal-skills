#!/usr/bin/env python3
"""How much naming does it take before the skill is used at all?

Arms A-D showed a binary: name the skill and it fires 32/32, phrase the request
naturally and it fires 0/32 whatever the description says. A binary that sharp
usually means the ladder has missing rungs. These are the rungs.

The decisive one is `route_asked`: the user does not name the skill but DOES ask
for one to be chosen. If that fires, the description works when routing is
attempted, and the failure is that routing is never attempted. If it does not
fire, the description is genuinely not selectable.
"""
import concurrent.futures, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.join(os.path.dirname(HERE), "probe-project")
PAIRS = [tuple(p) for p in json.load(open(os.path.join(HERE, "substitutions.json"),
                                          encoding="utf-8"))["pairs"]]
PASSAGES = [p for p in json.load(open(os.path.join(HERE, "passages.json"),
                                      encoding="utf-8")) if p["terms"]]

RUNGS = [
    ("1_slash",       "/copy-editor {text}"),
    ("2_named",       "Use the copy-editor skill. Clean up this text:\n\n{text}"),
    ("3_route_asked", "Use whichever of your skills fits, then clean up this "
                      "text:\n\n{text}"),
    ("4_skill_hinted","Check whether you have a skill for this, then clean up "
                      "this text:\n\n{text}"),
    # CONFOUNDED and kept to show it: "copy-edit" all but names `copy-editor`.
    # It belongs with the naming rungs, not with the natural ones.
    ("5_nearname",    "Run a copy-edit pass over this text:\n\n{text}"),
    # Genuinely natural: no word here appears in the skill's name.
    ("6_natural",     "make this sound like a person wrote it, not a model:\n\n{text}"),
    ("7_natural_ru",  "убери из этого текста признаки, что его писал AI:\n\n{text}"),
    ("8_polish",      "tidy up the wording here before I send it:\n\n{text}"),
]

def run(job):
    """One probe run. NEVER raises: a timeout inside `pool.map` kills the whole
    campaign, which is how the first ladder run lost 72 completed calls to one
    hung one."""
    rung, query, model = job
    try:
        p = subprocess.run(["claude", "-p", query, "--output-format", "json",
                            "--model", model],
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", cwd=PROJECT,
                           timeout=180)
    except subprocess.TimeoutExpired:
        return rung, None, 0.0
    try:
        env = json.loads(p.stdout)
    except json.JSONDecodeError:
        return rung, None, 0.0
    ans = env.get("result") or ""
    return rung, ans, env.get("total_cost_usd") or 0.0

def scored(before, after):
    done = avail = 0
    for a, b in PAIRS:
        if not re.search(rf"\b{re.escape(a)}\b", before, re.I):
            continue
        avail += 1
        done += bool(re.search(rf"\b{re.escape(b)}\b", after, re.I))
    return done, avail

model = sys.argv[1] if len(sys.argv) > 1 else "claude-haiku-4-5-20251001"
reps = int(sys.argv[2]) if len(sys.argv) > 2 else 2

# INSTALL the description rather than inheriting whatever is on disk. The first
# version read the file the candidate sweep was concurrently rewriting: the two
# campaigns shared one SKILL.md, and only the timing saved that run from being
# uninterpretable. A rig whose independent variable is set by another process is
# not a rig.
DESC_FILE = sys.argv[3] if len(sys.argv) > 3 else None
sys.path.insert(0, HERE)
import run_probe                                                # noqa: E402
if DESC_FILE == "real":
    desc = run_probe.REAL_DESCRIPTION
elif DESC_FILE:
    desc = open(DESC_FILE, encoding="utf-8").read().strip()
else:
    desc = run_probe.REAL_DESCRIPTION
run_probe.install(desc, PAIRS)
print(f"description installed: {desc[:88]}...\n")
jobs, meta = [], []
for _ in range(reps):
    for rung, tmpl in RUNGS:
        for p in PASSAGES:
            jobs.append((rung, tmpl.format(text=p["text"]), model))
            meta.append(p["text"])

agg = {r: [0, 0, 0, 0, 0.0, 0] for r, _ in RUNGS}  # done, avail, fired, runs, cost, dead
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
    for src, (rung, ans, cost) in zip(meta, pool.map(run, jobs)):
        g = agg[rung]
        if ans is None:                      # a dead run measures nothing
            g[5] += 1
            continue
        d, a = scored(src, ans)
        g[0] += d; g[1] += a; g[2] += bool(d); g[3] += 1; g[4] += cost

print(f"model {model}, {reps} reps x {len(PASSAGES)} passages per rung\n")
print(f"{'ступень':16} {'терминов':>12} {'доля':>7} {'прогонов сраб.':>16} {'мёртвых':>8}")
for rung, _ in RUNGS:
    d, a, f, n, c, dead = agg[rung]
    print(f"{rung:16} {f'{d}/{a}':>12} {d/a if a else 0:>7.2f} {f'{f}/{n}':>16} {dead:>8}")
print(f"\nстоимость: ${sum(g[4] for g in agg.values()):.2f}")
