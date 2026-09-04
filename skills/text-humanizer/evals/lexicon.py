#!/usr/bin/env python3
"""The marker detectors this eval set grades with, and where each one comes from.

Two sources, kept apart on purpose.

**Derived.** The word list of pattern 1 (AI Vocabulary) and the phrase list of
pattern 10 (Chatbotisms) are PARSED out of
`references/patterns_universal.md` on every call. A word added to that file
reaches this grader with no edit here, which is the property that stops the
eval from grading against yesterday's rules. `artifact-formalizer` buys the
same property by calling its shipped scanner; this skill ships no scanner, so
the reference file is read instead.

**Authored.** Patterns 3 (Negative Parallelism) and 9 (Em Dash Abuse) are
structural. Their entries in the reference file are example SENTENCES, not
surfaces, so no parse recovers a detector from them. The two regexes below are
written here and are the only part of this module that a reference-file edit
does not reach.

Every detector carries a probe: a string it must match. `build()` rejects a
detector that cannot match it, so a rule can never be added dead — the defect
`artifact-formalizer/references/measurement-baseline.md` section 5 records as
the one that let a lexicon entry ship as a silent zero.

The two authored detectors carry SEVERAL probes each, one per connector form.
A single declared example stands in for the whole class and passes by
construction: the first draft of the negative-parallelism regex accepted only
`;` and `but`, its one probe used `;`, and the detector scored zero on both
fixtures that carry the dash form. Measured on this repository, 2026-09-02.

Only priority `[A]` is graded by default. It is the class that fires at every
intensity, including `low` for technical text and `minimal` for legal text, so
it is the only class every case shares.
"""

import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
PATTERNS = os.path.join(SKILL, "references", "patterns_universal.md")

#: Words that carry no lexical content and would match everything.
_SECTION = re.compile(r"^## (\d+)\.\s*(.+?)\s*`\[([A-D])\]`\s*$", re.M)
#: `*   **Verbs:** delve, underscore, …` — the shape pattern 1 uses.
_VOCAB_LINE = re.compile(r"^\*\s+\*\*[^:*]+:\*\*\s*(.+?)\s*$", re.M)
#: `*   *AI:* "I hope this helps!" / "Certainly!"` — the shape pattern 10 uses.
_AI_LINE = re.compile(r"^\*\s+\*AI:\*\s*(.+?)\s*$", re.M)
_QUOTED = re.compile(r'"([^"]{2,})"')

#: A parenthetical qualifier is guidance for the reader, not part of the word.
_PAREN = re.compile(r"\s*\([^)]*\)")


class DeadDetector(RuntimeError):
    """A detector could not match its own probe. Its zero is not a measurement."""


class EmptyClass(RuntimeError):
    """A detector class parsed to nothing. The reference file moved under us."""


def _read(path=PATTERNS):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def sections(text=None):
    """Return `{number: {"title", "priority", "body"}}` for every pattern."""
    text = _read() if text is None else text
    hits = list(_SECTION.finditer(text))
    out = {}
    for i, m in enumerate(hits):
        end = hits[i + 1].start() if i + 1 < len(hits) else len(text)
        out[int(m.group(1))] = {"title": m.group(2),
                                "priority": m.group(3),
                                "body": text[m.end():end]}
    return out


def vocabulary(text=None, priority="A"):
    """Return the AI-vocabulary words, parsed from pattern 1.

    Trailing punctuation and any `(qualifier)` are stripped. A multi-word entry
    is kept whole; the matcher below anchors on word boundaries either way.
    """
    sec = sections(text).get(1)
    if not sec or sec["priority"] != priority:
        return []
    words = []
    for line in _VOCAB_LINE.findall(sec["body"]):
        for raw in line.split(","):
            word = _PAREN.sub("", raw).strip().strip(".").strip().lower()
            if word:
                words.append(word)
    return sorted(set(words))


def chatbotisms(text=None, priority="A"):
    """Return the chatbotism phrases, parsed from pattern 10's `*AI:*` line."""
    sec = sections(text).get(10)
    if not sec or sec["priority"] != priority:
        return []
    phrases = []
    for line in _AI_LINE.findall(sec["body"]):
        phrases.extend(p.strip() for p in _QUOTED.findall(line))
    return sorted({p for p in phrases if p})


def _word_re(term):
    """Match *term* and its inflections, on word boundaries.

    `delve` must reach `delved` and `delving`; `align` must reach `alignment`.
    A trailing `\\w*` is the whole mechanism, and it is why this counts hits
    rather than deciding them: `robust` reaches `robust_mode`, and the case key
    decides separately whether that occurrence was a term.
    """
    return re.compile(r"\b" + re.escape(term) + r"\w*", re.I)


def _phrase_re(phrase):
    """Match *phrase* with runs of whitespace collapsed and final `!`/`:` loose."""
    body = r"\s+".join(re.escape(w) for w in phrase.strip(" !:,.").split())
    return re.compile(body + r"[!:,.]*", re.I)


# --- the two authored detectors ------------------------------------------- #

#: Pattern 3. "not just X, but/it's Y" and its close relatives. The connector
#: is the load-bearing part: a bare "not just" is ordinary English.
NEGATIVE_PARALLELISM = re.compile(
    r"\bnot\s+(?:just|merely|simply|only)\b[^.!?\n]{0,80}?"
    r"(?:[;,—–-]\s*(?:it|this|that|they|we|you)(?:'s|\s+is|\s+are)\b|\bbut\b)",
    re.I)

#: Pattern 9. One em dash is punctuation. The reference file's own example
#: carries two in one sentence, so the detector reports OCCURRENCES and the
#: grader reports the rate per 100 words beside them.
EM_DASH = re.compile("[—–]")


#: `*   *AI:* "..." / "..."` — the example line each pattern carries. The two
#: authored detectors take their probes from HERE rather than from a list typed
#: into this file: an example a regex cannot match is then a red battery rather
#: than a silent divergence between the shipped document and the grader.
AI_EXAMPLE = re.compile(r"^\*\s+\*AI:\*\s*(.+)$", re.M)
QUOTED = re.compile(r"[\u201c\"]([^\u201d\"]+)[\u201d\"]")


def examples_for(pattern_number, text=None, minimum=1):
    """Return the quoted *AI:* examples the reference file gives for a pattern.

    Raises `EmptyClass` when the pattern is gone or its examples stop being
    quoted -- the same failure mode `vocabulary()` and `chatbotisms()` guard,
    applied to the two detectors that cannot be parsed into a word list.
    """
    sec = sections(text).get(pattern_number)
    if not sec:
        raise EmptyClass(f"pattern {pattern_number} is not in the reference file")
    found = []
    for line in AI_EXAMPLE.findall(sec["body"]):
        found.extend(q.strip() for q in QUOTED.findall(line))
    if len(found) < minimum:
        raise EmptyClass(
            f"pattern {pattern_number} yields {len(found)} quoted example(s), "
            f"need {minimum}; the detector would grade against nothing")
    return found


def build(text=None, priority="A"):
    """Return the detector roster, every entry probe-tested.

    Raises `EmptyClass` when a derived class parses to nothing and
    `DeadDetector` when any entry misses its own probe.
    """
    vocab = vocabulary(text, priority)
    bots = chatbotisms(text, priority)
    if not vocab:
        raise EmptyClass("pattern 1 (AI Vocabulary) parsed to zero words")
    if not bots:
        raise EmptyClass("pattern 10 (Chatbotisms) parsed to zero phrases")

    roster = []
    for word in vocab:
        roster.append({"kind": "ai_vocabulary", "source": "derived",
                       "term": word, "re": _word_re(word), "probe": word})
    for phrase in bots:
        roster.append({"kind": "chatbotism", "source": "derived",
                       "term": phrase, "re": _phrase_re(phrase),
                       "probe": phrase})
    # Probes: the reference file's OWN examples first, then the connector forms
    # the file does not illustrate. The first group makes the detector
    # accountable to the shipped document; the second covers the dash connector,
    # whose absence from a single probe once let the regex score zero on two
    # fixtures that carried it.
    roster.append({"kind": "negative_parallelism", "source": "authored",
                   "term": "not just X, but Y", "re": NEGATIVE_PARALLELISM,
                   "probes": examples_for(3, text, minimum=2) + [
                       "It is not just an update — it's a reimagining.",
                       "Not simply faster, but cheaper."]})
    roster.append({"kind": "em_dash", "source": "authored",
                   "term": "em dash", "re": EM_DASH,
                   "probes": examples_for(9, text, minimum=1) + [
                       "a leap – forward"]})

    dead = []
    for det in roster:
        for probe in det.get("probes") or [det["probe"]]:
            if not det["re"].search(probe):
                dead.append(f"{det['term']} misses {probe!r}")
    if dead:
        raise DeadDetector("; ".join(dead))
    return roster


def count(text, roster=None):
    """Return `{"total", "by_kind", "hits"}` for *text*.

    `hits` names the surface each detector matched, so a count is auditable
    against the document rather than taken on trust.
    """
    roster = build() if roster is None else roster
    by_kind, hits = {}, []
    for det in roster:
        found = det["re"].findall(text or "")
        if not found:
            continue
        n = len(found)
        by_kind[det["kind"]] = by_kind.get(det["kind"], 0) + n
        hits.append({"kind": det["kind"], "term": det["term"], "count": n})
    return {"total": sum(by_kind.values()), "by_kind": by_kind,
            "hits": sorted(hits, key=lambda h: (-h["count"], h["term"]))}


def main(argv=None):
    """Print the roster. `--count FILE` scores a file instead."""
    import argparse
    import json
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--count", metavar="FILE", help="score FILE and print JSON")
    ap.add_argument("--json", action="store_true", help="print the roster as JSON")
    args = ap.parse_args(argv)
    roster = build()
    if args.count:
        with open(args.count, encoding="utf-8") as fh:
            print(json.dumps(count(fh.read(), roster), ensure_ascii=False, indent=1))
        return 0
    if args.json:
        print(json.dumps([{k: v for k, v in d.items() if k != "re"}
                          for d in roster], ensure_ascii=False, indent=1))
        return 0
    derived = sum(1 for d in roster if d["source"] == "derived")
    print(f"{len(roster)} detectors live "
          f"({derived} derived from references/patterns_universal.md, "
          f"{len(roster) - derived} authored here)")
    for kind in sorted({d["kind"] for d in roster}):
        entries = [d for d in roster if d["kind"] == kind]
        print(f"  {kind:22} {len(entries):>3}  ({entries[0]['source']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
