#!/usr/bin/env python3
"""Does an `[A]` vocabulary word fire on correct usage? Spends no token.

Why this exists
---------------
`[A]` is the only priority class that reaches `low` and `minimal` intensity --
technical and legal text, where a changed word can change what the document
commits to. The class is a list of WORDS, not of meanings, so every entry is a
standing false-positive risk: `robust`, `dynamic`, `align`, `bridge` and
`highlight` all have ordinary correct uses.

`references/patterns_universal.md` answers this with a whitelist of three
evidence-bearing tests -- a habit in the voice passport, a domain term you can
point at, quoted material. The question this script answers is whether the
whitelist actually holds in practice, and it answers it from corpora already on
disk rather than from an opinion about the word list.

What it measures
----------------
For every `[A]` vocabulary word present in a fixture, the share of runs in which
the word SURVIVES, per arm. The comparison that matters is `with_skill` against
`baseline` on the same case: the baseline is an unaided model rewriting the same
text under the same instruction, so it is the fair reference for "would this
word have been kept anyway".

  same     the skill neither protects nor destroys the word
  better   the skill keeps it MORE often than no skill does
  worse    the skill removes it more often -- the false positive worth reading

Only cases carrying BOTH arms can be scored. A coverage case runs `with_skill`
alone and is listed separately as unpaired, because a survival rate with nothing
to compare it against says nothing about the rule.

What it does NOT establish
--------------------------
The words present in these fixtures are the words their authors put there, so
this is not a sample of English. A word absent from every fixture is unmeasured,
not innocent. And a single substitution can be harmless -- `were aligned` ->
`lined up` preserves the fact exactly -- so a `worse` row is the start of a
reading, not a verdict.

Usage
    python3 false_positive_sweep.py                    # every 2026-09-04 corpus
    python3 false_positive_sweep.py --corpus 'runs/*-corpus'
    python3 false_positive_sweep.py --word align       # one word
    python3 false_positive_sweep.py --json

Exit codes
  0  the sweep ran (a `worse` row is data, not a failure)
  3  the invocation is wrong: no eval file, no corpus matched
"""

import argparse
import collections
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import lexicon                                                # noqa: E402

DEFAULT_CORPUS_GLOB = os.path.join(HERE, "runs", "2026-09-04-*-corpus")


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def vocabulary():
    """The `[A]` word list, parsed from the shipped reference file.

    Parsed rather than restated: a word added to `patterns_universal.md` reaches
    this sweep with no edit here, which is the same contract `lexicon.py` keeps.
    """
    return sorted({d["term"].lower() for d in lexicon.build()
                   if d["kind"] == "ai_vocabulary"})


def survival(evals, corpus_glob, words):
    """Per (case, word), the share of runs keeping the word, for each arm."""
    rows, unpaired = [], []
    for case in evals["cases"]:
        fixture = _read(os.path.join(HERE, case["fixture"])).lower()
        present = [w for w in words if re.search(rf"\b{re.escape(w)}", fixture)]
        if not present:
            continue
        outputs = collections.defaultdict(list)
        for md in glob.glob(os.path.join(corpus_glob, case["id"], "*", "rep-*.md")):
            arm = os.path.basename(os.path.dirname(md))
            outputs[arm].append(_read(md).lower())
        if not outputs:
            continue
        paired = bool(outputs.get("baseline") and outputs.get("with_skill"))
        for word in present:
            rates = {}
            for arm, texts in outputs.items():
                kept = sum(1 for t in texts
                           if re.search(rf"\b{re.escape(word)}", t))
                rates[arm] = {"kept": kept, "runs": len(texts),
                              "rate": round(kept / len(texts), 3)}
            entry = {"case": case["id"], "genre": case["genre"],
                     "intensity": case.get("intensity_resolved"),
                     "word": word, "arms": rates}
            (rows if paired else unpaired).append(entry)
    return rows, unpaired


def classify(rows):
    out = {"same": [], "better": [], "worse": []}
    for r in rows:
        delta = r["arms"]["with_skill"]["rate"] - r["arms"]["baseline"]["rate"]
        r["delta"] = round(delta, 3)
        out["same" if abs(delta) < 1e-9 else
            ("better" if delta > 0 else "worse")].append(r)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--evals", default=os.path.join(HERE, "evals.json"))
    ap.add_argument("--corpus", default=DEFAULT_CORPUS_GLOB,
                    help="glob of campaign directories to read")
    ap.add_argument("--word", action="extend", nargs="+", metavar="W",
                    help="restrict the sweep to these words")
    ap.add_argument("--json", action="store_true")
    ap.exit_on_error = False
    try:
        args = ap.parse_args()
    except argparse.ArgumentError as exc:
        print(f"usage error: {exc}", file=sys.stderr)
        ap.print_usage(sys.stderr)
        return 3
    except SystemExit as exc:
        return 0 if getattr(exc, "code", 1) == 0 else 3

    if not os.path.isfile(args.evals):
        print(f"usage error: no eval file at {args.evals}", file=sys.stderr)
        return 3
    if not glob.glob(args.corpus):
        print(f"usage error: no campaign matched {args.corpus}", file=sys.stderr)
        return 3

    evals = json.loads(_read(args.evals))
    words = [w.lower() for w in args.word] if args.word else vocabulary()
    rows, unpaired = survival(evals, args.corpus, words)
    groups = classify(rows)

    if args.json:
        print(json.dumps({"paired": rows, "unpaired": unpaired,
                          "summary": {k: len(v) for k, v in groups.items()}},
                         ensure_ascii=False, indent=1))
        return 0

    low = [r for r in rows if r["intensity"] in ("low", "minimal")]
    print(f"[A] vocabulary: {len(words)} words")
    print(f"scored pairs  : {len(rows)} (case x word with BOTH arms); "
          f"{len(low)} of them at low/minimal, where [A] is the only class firing")
    print(f"unpaired      : {len(unpaired)} with_skill-only, not scored\n")

    for name, label in (("worse", "the skill removes it MORE often than no skill"),
                        ("better", "the skill KEEPS it more often than no skill"),
                        ("same", "no difference between the arms")):
        rs = groups[name]
        print(f"{name.upper():7} {len(rs):>3}  — {label}")
        for r in rs if name != "same" else []:
            b, w = r["arms"]["baseline"], r["arms"]["with_skill"]
            print(f"          {r['case']} ({r['intensity']}) {r['word']}: "
                  f"{b['kept']}/{b['runs']} -> {w['kept']}/{w['runs']}")
    print("\nA `worse` row is where to look, not a verdict: read the output and "
          "ask whether the\nsubstitution changed the fact or only the wording.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
