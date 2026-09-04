#!/usr/bin/env python3
"""Deterministic grader for the text-humanizer eval set (spec R1).

Grading spends no token and is a pure function of the committed corpus, the
case keys, and `references/patterns_universal.md`. There is no model judge:
every outcome is a string test or a ratio, so re-grading the same corpus
returns the same numbers.

**What this measures.** The mechanical contract: markers of the `[A]` class
removed, declared facts and terms carried through verbatim, a clean text left
close to unchanged, a short text answered at its own length.

**What it does not measure.** Whether the result reads as human-written. No
deterministic instrument reaches that, and the one measurement that bears on
it — Russell et al., ACL 2025 — used five expert readers, not a script. A
green run here says the skill did what it says it does, not that the output
passes a reader.

Exit codes
  0  graded, whatever the checks say — a failing check is data, not a defect
     of the instrument
  2  the instrument is broken: a dead detector, a malformed key
  3  the invocation is wrong: a missing eval file, an unreadable corpus
"""

import argparse
import difflib
import json
import os
import re
import sys

import lexicon

HERE = os.path.dirname(os.path.abspath(__file__))

#: A rewrite shorter than this is what a failed run leaves behind: the executor
#: writes whatever the envelope returned, and a transport error returns one
#: line that scores perfectly on every marker metric.
#:
#: Derivation: the shortest fixture is 296 characters; the transport-error
#: strings this harness has seen measure under 60. Any floor between the two
#: separates them. It is NOT a quality threshold.
MIN_CHARS = 80

#: Below this share of the key's `must_keep` anchors the answer is not a
#: rewrite of the fixture. The known way to reach it: `assets/generator_template.md`
#: opens with "generate a SYSTEM PROMPT" and closes with "Output the final
#: System Prompt", so a `with_skill` run can return a PROMPT instead of the
#: rewritten text. That is a finding about the skill, and it must not enter the
#: arm mean as a bad rewrite.
ANCHOR_FLOOR = 0.5

#: Signatures of `assets/generator_template.md` itself. A `with_skill` run that
#: returns the assembled SYSTEM PROMPT instead of the rewritten text is not a
#: bad rewrite -- it is not a rewrite at all -- and it must leave the arm mean
#: rather than drag it down as if the skill had edited badly.
#:
#: The anchor floor alone does NOT catch this. The emitted prompt QUOTES the
#: fixture inside itself, so a prompt dump can carry every `must_keep` anchor
#: and score 19/19 on facts while being 6x the source length and carrying 81
#: markers. Measured: P2/with_skill/rep-1, 2026-09-03 pressure campaign.
#: Two families, because the failure has two shapes. The run either echoes the
#: TEMPLATE it was handed, or it does what the template literally asks and
#: returns a freshly GENERATED system prompt -- which shares none of the
#: template's own wording and so needs its own signatures.
TEMPLATE_SIGNATURES = (
    # the template itself, echoed
    "you are an expert prompt engineer",
    "output the final system prompt",
    "instructions for the generated prompt",
    "the prompt you generate must include",
    # a generated system prompt: instruction language about editing, which a
    # rewritten runbook, memo or article has no reason to contain
    "traffic-light",
    "traffic light system",
    "ai markers detected",
    "anti-pattern list",
    "anti-pattern",
    "rewriting a clean paragraph",
    "voice passport",
    "role definition",
    "intensity:",
)

#: How many signatures make it a prompt rather than a coincidence. One phrase
#: could plausibly be quoted by a rewrite whose SUBJECT is prompt engineering;
#: two together in a rewritten runbook cannot.
TEMPLATE_HITS = 2

#: The structural net, independent of wording. A rewrite is about the length of
#: its source. Something three times longer that also carries three times the
#: markers is a different document, whatever it says.
RUNAWAY_GROWTH = 3.0
RUNAWAY_MARKER_RATIO = 3.0


def returned_the_prompt(result_text):
    """Return the prompt signatures present in *result_text*."""
    low = (result_text or "").lower()
    return [s for s in TEMPLATE_SIGNATURES if s in low]

_WORD = re.compile(r"\S+")

#: Digits in a claim. `2.4`, `10,000`, `3.2`, `84`.
_NUMBER = re.compile(r"\d[\d,.]*\d|\d")

#: Spelled-out numbers a source may use where the rewrite uses digits. Only the
#: SOURCE side is normalised: a rewrite turning `twenty minutes` into
#: `20 minutes` restates a figure that was there, and must not be reported as
#: an invention.
_NUMBER_WORDS = {
    "zero": "0", "one": "1", "two": "2", "three": "3", "four": "4",
    "five": "5", "six": "6", "seven": "7", "eight": "8", "nine": "9",
    "ten": "10", "eleven": "11", "twelve": "12", "thirteen": "13",
    "fourteen": "14", "fifteen": "15", "sixteen": "16", "seventeen": "17",
    "eighteen": "18", "nineteen": "19", "twenty": "20", "thirty": "30",
    "forty": "40", "fifty": "50", "sixty": "60", "seventy": "70",
    "eighty": "80", "ninety": "90", "hundred": "100", "thousand": "1000",
    "million": "1000000", "billion": "1000000000",
}


def _numbers(text, expand_words=False):
    """Return the numeric tokens in *text*, commas and trailing dots stripped.

    `expand_words` adds the digit form of any spelled-out number, and is used on
    the SOURCE side only.
    """
    found = {m.group(0).replace(",", "").rstrip(".")
             for m in _NUMBER.finditer(text or "")}
    if expand_words:
        low = (text or "").lower()
        for word, digits in _NUMBER_WORDS.items():
            if re.search(r"\b" + word + r"\b", low):
                found.add(digits)
    return {n for n in found if n}


def invented_numbers(source, result):
    """Numeric tokens in *result* that appear nowhere in *source*.

    This closes the trap `docs/Manuals/skill-evals_guide.md` section 6.3 names:
    a `must_keep` anchor is a "contains the string" test, and a rewrite that
    invented a benchmark while keeping `840 ms` would pass it. A figure the
    source does not hold is the fabrication mode these fixtures can actually
    produce, and it is decidable without a model.

    It does not reach an invented CLAIM in words. No deterministic test does;
    `evals/README.md` states that limit rather than implying coverage.
    """
    return sorted(_numbers(result) - _numbers(source, expand_words=True))


class KeyMalformed(RuntimeError):
    """A case key does not carry the fields the grader reads."""


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _load_key(path):
    data = json.loads(_read(path))
    for field in ("must_keep", "must_drop"):
        if not isinstance(data.get(field), list):
            raise KeyMalformed(f"{path}: {field} must be a list")
    # `must_not_appear` is optional and defaults to empty, so every key written
    # before it existed still loads.
    extra = data.setdefault("must_not_appear", [])
    if not isinstance(extra, list):
        raise KeyMalformed(f"{path}: must_not_appear must be a list")
    return data


def _words(text):
    return len(_WORD.findall(text or ""))


def _norm(text):
    """Collapse whitespace so a reflowed line is not counted as an edit."""
    return " ".join((text or "").split())


def similarity(source, result):
    """Character-level ratio of *result* to *source*, whitespace-normalised."""
    return round(difflib.SequenceMatcher(
        None, _norm(source), _norm(result)).ratio(), 4)


def _present(needle, haystack):
    """Is *needle* in *haystack*? Case-insensitive, whitespace-normalised.

    A `must_keep` anchor is either a string -- matched exactly -- or a LIST of
    surface forms, any one of which satisfies it. The list states which forms
    express the same fact; it does not loosen the test.

    Why the list exists, and when it must not be used. Literal matching cannot
    tell "the fact is gone" from "the fact was rephrased": a run that returned
    `40 a week` for `40 per week`, and `Eighty-four pounds` for `84 pounds`,
    scored as fact loss. Those are the same fact in another surface. A short
    company name standing where the full legal name belongs is NOT, so
    `Northwind Analytics` carries no alternative and still fails when only
    `Northwind` comes back.

    The mechanism was added after a campaign showed those two forms, so a
    reader should know the keys moved once in response to observed output.
    Each alternative is justified in its key's `must_keep_notes`.
    """
    forms = needle if isinstance(needle, list) else [needle]
    hay = _norm(haystack).lower()
    return any(_norm(f).lower() in hay for f in forms)


def _label(needle):
    """How an anchor is named in a report: the first form stands for the set."""
    return needle[0] if isinstance(needle, list) else needle


#: A trailing block that TALKS ABOUT the edit instead of being it. The shared
#: task says "Return ONLY the rewritten text. No preamble, no commentary", so
#: such a block is a contract violation in its own right -- and it also
#: corrupts every other check, because `must_drop` and the marker count match a
#: substring ANYWHERE in the answer.
#:
#: Measured: P4/with_skill/rep-3 rewrote the page correctly, then appended a
#: note to the compiler quoting the `[TBD]` it had just removed. The grader
#: scored that as "the placeholder survived" and as 34% length growth -- two
#: failures for one violation, and neither of them the one that happened. It is
#: 1 run in 221, so this guard exists to score correctly, not because the skill
#: has a commentary habit.
_FIRST_PERSON = re.compile(
    r"\b(I|I'm|I've|my|we|note|flag|caveat|heads[- ]up)\b", re.I)
_ABOUT_THE_EDIT = re.compile(
    r"\b(draft|rewrite|rewritten|edit|edited|version|source|original|"
    r"placeholder|invent|if you|let me know|send it)\b", re.I)
#: Longer than this and it is not a note, it is the answer.
COMMENTARY_MAX_WORDS = 140


def split_commentary(result_text):
    """Return (the copy, the trailing note or "").

    A note is the last block, set off by a blank line or a horizontal rule,
    which speaks in the first person ABOUT the edit. Both conditions are
    required: prose legitimately says "I" (P1's memo does), and prose
    legitimately says "draft" -- only the pair marks a note about the work.
    """
    text = (result_text or "").rstrip()
    parts = re.split(r"\n\s*(?:---+|\*\*\*+|___+)\s*\n|\n\n", text)
    if len(parts) < 2:
        return text, ""
    tail = parts[-1].strip()
    if (tail and len(tail.split()) <= COMMENTARY_MAX_WORDS
            and _FIRST_PERSON.search(tail) and _ABOUT_THE_EDIT.search(tail)):
        return text[: text.rfind(tail)].rstrip().rstrip("-*_ \n"), tail
    return text, ""


def score_run(fixture_text, result_text, key, roster, meta=None):
    """Return every value and check for one arm of one case."""
    meta = meta or {}
    # The COPY is what the other checks grade. A trailing note about the edit is
    # a violation of its own, scored once below, and it must not also make the
    # removal checks and the length ratio read as failures of the rewrite.
    copy_text, commentary = split_commentary(result_text)
    before = lexicon.count(fixture_text, roster)
    after = lexicon.count(copy_text, roster)

    kept = [s for s in key["must_keep"] if _present(s, result_text)]
    lost = [_label(s) for s in key["must_keep"] if s not in kept]
    survived = [s for s in key["must_drop"] if _present(s, copy_text)]

    # `must_drop` and `must_not_appear` are opposite intents and the difference
    # is load-bearing. A `must_drop` surface IS in the fixture and the run has
    # to take it out; TC-EV-27 refuses one that is absent, because a removal
    # check for something never present passes without measuring anything. A
    # `must_not_appear` surface is NOT in the fixture and the run must not put
    # it there -- the reinjection guard of guide section 6.6, and the failure
    # mode the skill's own doctrine names: over-editing INTRODUCES the patterns
    # the pass exists to remove. Conflating them would make one of the two
    # unexpressible.
    reinjected = [s for s in key.get("must_not_appear", [])
                  if _present(s, copy_text)]

    anchors = len(key["must_keep"])
    anchor_share = (len(kept) / anchors) if anchors else 1.0
    chars = len(result_text.strip())

    echoed = returned_the_prompt(result_text)
    # Computed BEFORE the validity chain, which reads them. They used to be
    # derived after it, which is fine until a guard needs them.
    ratio = similarity(fixture_text, copy_text)
    growth = round(_words(copy_text) / _words(fixture_text), 3) if _words(fixture_text) else None

    if meta.get("is_error"):
        reason = f"the run reported an error: {meta.get('error')}"
    elif len(echoed) >= TEMPLATE_HITS:
        reason = (f"the answer is a SYSTEM PROMPT, not a rewrite: it carries "
                  f"{len(echoed)} prompt signature(s) {echoed}. This is a finding "
                  f"about the skill, not a bad edit, and it does not enter the "
                  f"arm mean")
    elif (growth is not None and growth >= RUNAWAY_GROWTH
          and before["total"] and after["total"] >= before["total"] * RUNAWAY_MARKER_RATIO):
        reason = (f"{growth}x the source length carrying {after['total']} markers "
                  f"against the source's {before['total']}; that is a different "
                  f"document, not a rewrite of this one")
    elif chars < MIN_CHARS:
        reason = (f"{chars} characters, under the {MIN_CHARS}-character floor; "
                  f"this is a failed run, not a rewrite")
    elif anchor_share < ANCHOR_FLOOR:
        reason = (f"{len(kept)} of {anchors} anchors survived, under the "
                  f"{ANCHOR_FLOOR:.0%} floor; the answer is not a rewrite of "
                  f"this fixture")
    else:
        reason = None

    invented = invented_numbers(fixture_text, copy_text)

    checks = [
        {"name": "no_commentary", "passed": not commentary,
         "detail": ("clean" if not commentary else
                    f"{len(commentary.split())} words of note about the edit "
                    f"follow the copy: {commentary[:60]!r}...")},
        {"name": "no_invented_numbers", "passed": not invented,
         "detail": f"{len(invented)} figure(s) absent from the source"
                   + (f": {invented}" if invented else "")},
        {"name": "facts_kept", "passed": not lost,
         "detail": f"{len(kept)}/{anchors} kept" + (f", lost: {lost}" if lost else "")},
        {"name": "markers_removed", "passed": not survived,
         "detail": f"{len(survived)}/{len(key['must_drop'])} declared surfaces survived"
                   + (f": {survived}" if survived else "")},
    ]
    if key.get("must_not_appear"):
        checks.append({"name": "no_reinjection", "passed": not reinjected,
                       "detail": f"{len(reinjected)}/"
                                 f"{len(key['must_not_appear'])} guarded "
                                 f"surfaces appeared"
                                 + (f": {reinjected}" if reinjected else "")})
    if key.get("min_similarity") is not None:
        checks.append({"name": "not_over_edited",
                       "passed": ratio >= key["min_similarity"],
                       "detail": f"similarity {ratio} against a floor of "
                                 f"{key['min_similarity']}"})
    if key.get("max_growth") is not None:
        checks.append({"name": "proportionate_length",
                       "passed": growth is not None and growth <= key["max_growth"],
                       "detail": f"growth {growth}x against a ceiling of "
                                 f"{key['max_growth']}x"})

    return {
        "measured": reason is None,
        "unmeasured_reason": reason,
        "markers_before": before["total"],
        "markers_after": after["total"],
        "markers_by_kind_after": after["by_kind"],
        "markers_surviving": after["hits"],
        "invented_numbers": invented,
        "facts_kept": len(kept),
        "facts_total": anchors,
        "facts_lost": lost,
        "declared_surfaces_surviving": survived,
        "reinjected_surfaces": reinjected,
        "template_signatures": echoed,
        "commentary": commentary,
        "commentary_words": len(commentary.split()) if commentary else 0,
        "similarity": ratio,
        "growth": growth,
        "words": _words(result_text),
        "chars": chars,
        "checks": checks,
        "checks_passed": sum(1 for c in checks if c["passed"]),
        "checks_total": len(checks),
    }


def grade(evals, corpus_root, roster):
    """Score every run present under *corpus_root*."""
    cases = []
    for case in evals["cases"]:
        fixture_text = _read(os.path.join(HERE, case["fixture"]))
        key = _load_key(os.path.join(HERE, case["key"]))
        arms = {}
        for arm in ("baseline", "with_skill"):
            arm_dir = os.path.join(corpus_root, case["id"], arm)
            if not os.path.isdir(arm_dir):
                continue
            reps = []
            for name in sorted(os.listdir(arm_dir)):
                if not name.endswith(".md"):
                    continue
                rep_path = os.path.join(arm_dir, name)
                meta_path = rep_path[:-3] + ".meta.json"
                meta = json.loads(_read(meta_path)) if os.path.isfile(meta_path) else {}
                scored = score_run(fixture_text, _read(rep_path), key, roster, meta)
                scored["rep"] = name[:-3]
                scored["model"] = meta.get("model")
                scored["cost_usd"] = meta.get("total_cost_usd")
                reps.append(scored)
            if reps:
                arms[arm] = reps
        cases.append({
            "id": case["id"], "name": case["name"], "genre": case["genre"],
            "intensity_resolved": case.get("intensity_resolved"),
            "measures": case.get("measures"),
            "control": bool(case.get("control")),
            "markers_in_fixture": lexicon.count(fixture_text, roster)["total"],
            "arms": arms,
        })
    return cases


def provenance(cases, corpus_root, roster):
    """What produced these numbers, recorded beside them.

    Guide section 8: an eval goes stale when the skill contract, the model or
    the environment moves under it, and the report is the only place a reader
    can find out which of those happened. The per-run metadata already carries a
    fingerprint of the exact assembled prompt; this lifts it into the report so
    a stale figure can be identified as stale without opening the corpus.
    """
    skill_md = os.path.join(os.path.dirname(HERE), "SKILL.md")
    version = None
    try:
        m = re.search(r"^version:\s*(.+)$", _read(skill_md), re.M)
        version = m.group(1).strip() if m else None
    except OSError:
        pass
    # Read the corpus metadata rather than the graded runs: `grade()` keeps only
    # what a check needs, and widening its return value to carry provenance
    # would put the whole envelope into every report.
    # `styles` is read from the metadata rather than taken from the case dict:
    # `grade()` does not carry `style`, so `case.get("style")` was always None
    # and every cross-style case (S1-S4) re-assembled without its style file and
    # reported STALE against a corpus drawn minutes earlier. The metadata records
    # what was actually used, which is the right source for a provenance check.
    models, prompts, tasks, fixtures, styles = set(), {}, {}, {}, {}
    for case in cases:
        for arm in ("baseline", "with_skill"):
            arm_dir = os.path.join(corpus_root, case["id"], arm)
            if not os.path.isdir(arm_dir):
                continue
            for name in sorted(os.listdir(arm_dir)):
                if not name.endswith(".meta.json"):
                    continue
                try:
                    meta = json.loads(_read(os.path.join(arm_dir, name)))
                except (OSError, json.JSONDecodeError):
                    continue
                if meta.get("model"):
                    models.add(meta["model"])
                if arm == "with_skill" and meta.get("skill_prompt_sha256_16"):
                    prompts[case["id"]] = meta["skill_prompt_sha256_16"]
                if meta.get("task_sha256_16"):
                    tasks[case["id"]] = meta["task_sha256_16"]
                if meta.get("fixture_sha256_16"):
                    fixtures[case["id"]] = meta["fixture_sha256_16"]
                if arm == "with_skill":
                    styles[case["id"]] = meta.get("style")
    # Does each recorded prompt still match what humanizer.py assembles today?
    # This is the whole point of recording the hash, and it is computed here
    # rather than left to a reader who would have to know to check.
    import run_humanize                                        # noqa: PLC0415
    stale = []
    for case in cases:
        recorded = prompts.get(case["id"])
        if not recorded:
            continue
        try:
            today = run_humanize._sha(run_humanize.assemble_skill_prompt(
                case["genre"], style=styles.get(case["id"])))
        except Exception:                                      # noqa: BLE001
            continue
        if recorded != today:
            stale.append(case["id"])

    return {
        "skill_version": version,
        "corpus": os.path.basename(os.path.normpath(corpus_root)),
        "models": sorted(models),
        "detectors": len(roster),
        "detectors_derived": sum(1 for d in roster if d["source"] == "derived"),
        "skill_prompt_sha256_16": prompts,
        "task_sha256_16": tasks,
        "fixture_sha256_16": fixtures,
        "stale_vs_today": sorted(stale),
        "stale_note": (
            "Cases whose recorded skill prompt no longer matches what "
            "humanizer.py assembles today. Their figures describe a DIFFERENT "
            "skill and must not be quoted as current -- guide section 8. Empty "
            "is the healthy state; a non-empty list means re-draw."
            if stale else
            "Every case was measured against the prompt humanizer.py assembles "
            "today."),
    }


def summarise(cases):
    """Return the per-arm totals a reader looks at first."""
    out = {}
    for arm in ("baseline", "with_skill"):
        reps = [r for c in cases for r in c["arms"].get(arm, [])]
        measured = [r for r in reps if r["measured"]]
        out[arm] = {
            "runs": len(reps),
            "measured": len(measured),
            "unmeasured": len(reps) - len(measured),
            "checks_passed": sum(r["checks_passed"] for r in reps),
            "checks_total": sum(r["checks_total"] for r in reps),
            "markers_after_total": sum(r["markers_after"] for r in measured),
            "facts_lost_total": sum(len(r["facts_lost"]) for r in measured),
            "cost_usd": round(sum(r["cost_usd"] or 0 for r in reps), 4),
        }
    return out


def render(cases, summary, roster):
    lines = []
    derived = sum(1 for d in roster if d["source"] == "derived")
    lines.append(f"DETECTORS  {len(roster)} live "
                 f"({derived} derived from references/patterns_universal.md, "
                 f"{len(roster) - derived} authored in lexicon.py)")
    lines.append("")
    for case in cases:
        head = (f"{case['id']}  {case['name']}  "
                f"[genre {case['genre']} -> intensity {case['intensity_resolved']}]")
        lines.append(head)
        lines.append(f"     measures: {case['measures']}")
        lines.append(f"     fixture carries {case['markers_in_fixture']} [A] markers")
        for arm in ("baseline", "with_skill"):
            for rep in case["arms"].get(arm, []):
                tag = f"{arm}/{rep['rep']}"
                if not rep["measured"]:
                    lines.append(f"     {tag:24} NOT MEASURED — {rep['unmeasured_reason']}")
                    continue
                verdict = "ok " if rep["checks_passed"] == rep["checks_total"] else "FAIL"
                lines.append(
                    f"     {tag:24} {verdict}  markers {rep['markers_before']}->"
                    f"{rep['markers_after']}   facts {rep['facts_kept']}/"
                    f"{rep['facts_total']}   sim {rep['similarity']}   "
                    f"growth {rep['growth']}x")
                for check in rep["checks"]:
                    if not check["passed"]:
                        lines.append(f"       - {check['name']}: {check['detail']}")
        lines.append("")
    lines.append("SUMMARY")
    for arm, s in summary.items():
        lines.append(
            f"  {arm:12} {s['measured']}/{s['runs']} measured   "
            f"checks {s['checks_passed']}/{s['checks_total']}   "
            f"markers left {s['markers_after_total']}   "
            f"facts lost {s['facts_lost_total']}   ${s['cost_usd']}")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--evals", default=os.path.join(HERE, "evals.json"))
    ap.add_argument("--corpus", default=os.path.join(HERE, "runs", "2026-09-04-full-corpus"),
                    help="campaign directory under runs/ to grade")
    ap.add_argument("--out", help="write the full report as JSON to this path")
    ap.add_argument("--json", action="store_true", help="print JSON to stdout")
    ap.exit_on_error = False
    try:
        args = ap.parse_args(argv)
    except (argparse.ArgumentError, SystemExit) as exc:
        code = getattr(exc, "code", 1)
        return 0 if code == 0 else 3

    if not os.path.isfile(args.evals):
        print(f"usage error: no eval file at {args.evals}", file=sys.stderr)
        return 3
    if not os.path.isdir(args.corpus):
        print(f"usage error: no corpus at {args.corpus}", file=sys.stderr)
        return 3

    try:
        roster = lexicon.build()
    except (lexicon.DeadDetector, lexicon.EmptyClass) as exc:
        print(f"instrument broken: {exc}", file=sys.stderr)
        return 2

    with open(args.evals, encoding="utf-8") as fh:
        evals = json.load(fh)
    try:
        cases = grade(evals, args.corpus, roster)
    except KeyMalformed as exc:
        print(f"instrument broken: {exc}", file=sys.stderr)
        return 2
    summary = summarise(cases)
    report = {"schema": "humanizer-evals-report/v1",
              "detectors": len(roster),
              "provenance": provenance(cases, args.corpus, roster),
              "cases": cases, "summary": summary}

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        print(render(cases, summary, roster))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(report, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
