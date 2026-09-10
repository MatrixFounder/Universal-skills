#!/usr/bin/env python3
"""Check that a Markdown conversion still contains what the PDF said.

Why this exists
---------------
"Convert this PDF to Markdown" has no natural acceptance test, so the usual
one is reading a few pages and hoping. That misses exactly the failures that
matter, because the dangerous ones are *silent and structural*: a filter that
drops a whole chapter, a list-continuation rule that severs every second
paragraph, a table whose rows never made it out. Both of those shipped in a
measured 1206-page conversion and both were caught by this comparison, not by
reading.

The check is deliberately one-directional and coarse: every word the PDF holds
should appear at least as many times in the Markdown. It does not judge order,
formatting or structure — it answers "did anything vanish", which is the
question a converter cannot answer about itself.

What it normalises, and why each one is required
------------------------------------------------
Without normalisation the report drowns in false positives and the real
findings never surface:

* **Markdown syntax and escapes** — ``MKT\\_AGENCY`` is the same token as
  ``MKT_AGENCY``; leaving the backslash in reported every escaped identifier
  in the document as missing.
* **Hyphenation** — a justified line break splits ``Orchestra-`` / ``tion``,
  and a converter that rejoins it correctly would otherwise be *penalised* for
  the repair. Both sides are de-hyphenated so the comparison is fair. This
  makes the comparison fair; it does not make it able to *see* hyphenation —
  see the second limitation below.
* **Running headers and footers** — excluded, because a converter is supposed
  to drop them and counting them as loss buried the signal under ~1600 tokens
  on one document. Two rules, picked by what the source can actually support:
  from a PDF, *the same word, in the same place, on many pages* (positional,
  per word instance); from a dump, which carries no geometry, repetition of a
  whole line near the top or bottom of the reading order. The report says
  which, in ``furniture_granularity`` and ``reference_source``.
* **Contents pages** — dotted-leader pages are skipped: a converter that
  replaces them with a generated table of contents is not losing content.

Known and deliberate #1: a table whose header repeats on every page it spans
is counted as loss when the converter stitches the table and emits the header
once. That is correct behaviour scoring as a miss, so read the *top missing
tokens* before believing a number -- a handful of column names repeating is
this, not a bug.

Known and deliberate #2 -- **a hyphenation defect is invisible to this check
by construction, and no number in this report can be read as evidence about
one.** ``_WORD`` is ``\\w{3,}``, which does not match a hyphen at all, so
a line-broken ``two-`` / ``dimensional`` and a badly welded ``two- dimensional``
produce the *same* Counter whatever ``dehyphenate`` decided: both tokenise
identically whether the join was right, wrong, or never attempted, so a
converter that welds ``o-`` and ``end`` into ``o- end`` scores zero loss here.
De-hyphenation below therefore exists only to keep the comparison *fair*, and
never to grade it. Whether a line-ending hyphen was resolved correctly is
``_textlines.hyphen_verdict`` / ``hyphen_sites``'s question, asked against the
PDF's own line ends -- not this module's.

Usage
-----
    python3 scripts/pdf_verify_md.py SOURCE OUT.md [--max-loss PCT]
                                     [--top N] [--json] [--json-errors]

``SOURCE`` is either the PDF itself or a ``pdf_extract.py`` dump (``.json``);
the dump is far faster on a long document and is preferred when you have one.

Exit codes: ``0`` checked (and within ``--max-loss`` if given); ``1``
unreadable input, or loss above ``--max-loss``; ``2`` usage.

What it REFUSES to score, rather than scoring 0 % loss (all exit ``1``):

* a ``SOURCE`` ``.json`` that is not a ``pdf_extract.py`` dump, or a dump with
  no pages (``NotADump`` / ``EmptyReference``);
* any reference that tokenises to nothing -- a scan, a PDF with no text layer,
  a document whose every page is a contents page (``EmptyReference``);
* an encrypted PDF, named as such and pointed at ``--password``
  (``EncryptedPDF``).

Each of those used to report ``PDF tokens 0, missing 0 (0.0%)`` and exit ``0``
**even under ``--max-loss 0``**, which made this gate certify Markdown it had
never compared against anything.
"""

from __future__ import annotations

import _venv_bootstrap  # self-bootstrap into scripts/.venv (CLAUDE.md §2)
_venv_bootstrap.reexec_into_venv(requires=("pdfplumber",), _file=__file__)

import argparse
import collections
import json
import re
import sys
from pathlib import Path

from _errors import (add_json_errors_argument, install_human_channel,
                     report_error, write_json_stdout, write_text_stdout)

_WORD = re.compile(r"\w{3,}", re.UNICODE)
_HYPHEN_END = ("-", "\u00ad")   # U+002D, and SOFT HYPHEN (always discretionary)
_DOTS = re.compile(r"(?:\.\s?){4,}")
_DIGITS = re.compile(r"\d+")

# Markdown scaffolding that is formatting, not content.
_MD_STRIP = (
    (re.compile(r"^```.*$", re.M), " "),            # fences (keep the code)
    (re.compile(r"!\[[^\]]*\]\([^)]*\)"), " "),     # images
    (re.compile(r"\[([^\]]*)\]\([^)]*\)"), r"\1"),  # links -> their text
    (re.compile(r"^\s{0,3}#{1,6}\s+", re.M), " "),  # heading markers
    (re.compile(r"^\s*>\s?", re.M), " "),           # blockquote markers
    (re.compile(r"^\s*\|[-: |]+\|\s*$", re.M), " "),  # table delimiter rows
    (re.compile(r"[|*`~]"), " "),                   # cell/emphasis/code marks
    (re.compile(r"\\(.)"), r"\1"),                  # markdown escapes
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdf_verify_md.py",
        description="Verify that a Markdown conversion kept the PDF's words.")
    parser.add_argument("SOURCE", type=Path,
                        help="The source PDF, or a pdf_extract.py dump (.json).")
    parser.add_argument("MARKDOWN", type=Path, help="The converted .md file.")
    parser.add_argument("--max-loss", type=float, default=None, metavar="PCT",
                        help="Exit 1 when more than PCT%% of the PDF's tokens "
                             "are missing. Omit to report without failing.")
    parser.add_argument("--top", type=int, default=25, metavar="N",
                        help="How many missing tokens / worst pages to list "
                             "(default %(default)s).")
    parser.add_argument("--password", default=None, metavar="PW",
                        help="Password, when SOURCE is an encrypted PDF.")
    parser.add_argument("--json", action="store_true",
                        help="Emit the report as JSON.")
    add_json_errors_argument(parser)
    return parser


def dehyphenate(text: str) -> str:
    """Rejoin a word split by a line-ending hyphen.

    Two characters end a split word here: ``-`` U+002D and U+00AD SOFT
    HYPHEN, which is discretionary by definition and so is always dropped.
    The hyphen is kept when the fragment before it already contains ``.``,
    ``/`` or ``:`` — that is a real hyphen inside an identifier or a URL
    (``sap.hana-`` / ``app``), not the typesetter's.

    Honest scope: this is normalisation, not detection. Both sides of the
    comparison run through it, so the *tokens* agree; the hyphen itself is
    outside ``_WORD`` and can never reach the report (see "Known and
    deliberate #2" above). U+2010/U+2011/U+2012 are deliberately absent: they
    are typographic hyphens a converter is supposed to *keep*, and the module
    that judges them is ``_textlines.hyphen_verdict``.
    """
    out: list[str] = []
    for line in text.split("\n"):
        if out and out[-1].endswith(_HYPHEN_END):
            token = re.split(r"[\s(\[]", out[-1].rstrip("-\u00ad"))[-1]
            if line[:1].isalpha():
                soft = out[-1].endswith("\u00ad")
                real = (not soft) and any(ch in token for ch in "./:")
                out[-1] = (out[-1] if real else out[-1][:-1]) + line
                continue
        out.append(line)
    return "\n".join(out)


def tokens(text: str) -> collections.Counter:
    """Word counts, with boundary underscores stripped off each token.

    Python's ``\\w`` includes ``_``, so ``_Finnegans Wake_`` would otherwise
    tokenise as ``_finnegans`` + ``wake_`` and neither would match the PDF:
    202 distinct tokens / 314 occurrences on one measured document, a third of
    its whole reported loss. The strip is applied to an already-matched token
    and symmetrically to both sides, so ``MKT_AGENCY`` and ``snake_case_name``
    stay whole -- ``_`` is deliberately *not* in ``_MD_STRIP``, where it would
    split them. ``len >= 3`` is re-checked after the strip so a bare ``___``
    does not become an empty token.
    """
    c: collections.Counter = collections.Counter()
    for w in _WORD.findall(dehyphenate(text)):
        w = w.strip("_")
        if len(w) >= 3:
            c[w.lower()] += 1
    return c


def strip_markdown(text: str) -> str:
    for pattern, repl in _MD_STRIP:
        text = pattern.sub(repl, text)
    return text


class _SourceRefused(Exception):
    """A reference this check cannot honestly score a conversion against.

    Carries the ``--json-errors`` envelope ``type`` so ``main`` can name the
    cause instead of flattening everything into ``VerifyFailed``.
    """

    def __init__(self, message: str, *, error_type: str, details=None):
        super().__init__(message)
        self.error_type = error_type
        self.details = details


def _page_texts(source: Path) -> list[tuple[int, str]]:
    """The per-page text of a ``pdf_extract.py`` dump, in reading order.

    Refuses anything that is not a dump instead of scoring it. ``.get("pages",
    [])`` on a stray JSON file used to yield "PDF tokens 0, missing 0 (0.0%)"
    and **exit 0 even under ``--max-loss 0``** -- ``echo '{}' > bad.json``
    certified any Markdown as green, and this is the acceptance gate the
    recipe in ``SKILL.md`` publishes. A gate that cannot fail is not a gate.
    """
    try:
        dump = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise _SourceRefused(
            f"{source} is not valid JSON, so it cannot be a pdf_extract.py "
            f"dump: {exc}. Pass the PDF itself, or a dump written by "
            f"pdf_extract.py -o.",
            error_type="NotADump", details={"path": str(source)}) from exc
    if not isinstance(dump, dict) or not isinstance(dump.get("pages"), list):
        raise _SourceRefused(
            f"{source} is JSON but not a pdf_extract.py dump: no top-level "
            f"`pages` list. Pass the PDF itself, or a dump written by "
            f"pdf_extract.py -o.",
            error_type="NotADump", details={"path": str(source)})
    if not dump["pages"]:
        raise _SourceRefused(
            f"{source} is a dump of 0 pages, so there is nothing to compare "
            f"the Markdown against. Re-run pdf_extract.py on the source PDF.",
            error_type="EmptyReference",
            details={"path": str(source), "pages": 0})
    return [(p.get("n", i + 1), p.get("text") or "")
            for i, p in enumerate(dump["pages"])]


def _is_password_failure(exc: BaseException) -> bool:
    """True when `exc` means "wrong or missing PDF password".

    pdfplumber re-raises pdfminer's `PDFPasswordIncorrect` wrapped in its own
    `PdfminerException`, and BOTH have an empty `str()` -- interpolating the
    exception produced the message `Verification failed: ` and sent nobody to
    `--password`. So the class is matched, not the text, through the wrapper's
    `args` and `__cause__`.
    """
    try:
        from pdfminer.pdfdocument import PDFPasswordIncorrect
    except ImportError:      # pragma: no cover - pdfplumber's own dependency
        return False
    seen: list = [exc]
    for _ in range(8):       # bounded: a wrapper chain, not a search
        if not seen:
            break
        current = seen.pop()
        if isinstance(current, PDFPasswordIncorrect):
            return True
        seen.extend(a for a in getattr(current, "args", ())
                    if isinstance(a, BaseException))
        if current.__cause__ is not None:
            seen.append(current.__cause__)
    return False


def _page_words(source: Path, password) -> list[tuple[int, list]]:
    """Every word of every page, with its geometry, straight from pdfplumber."""
    import pdfplumber  # deferred: only the PDF path needs it
    out: list[tuple[int, list]] = []
    try:
        opened = pdfplumber.open(str(source), password=password or "")
    except Exception as exc:
        if _is_password_failure(exc):
            raise _SourceRefused(
                f"PDF is encrypted and could not be opened — supply a correct "
                f"--password: {source}",
                error_type="EncryptedPDF",
                details={"path": str(source)}) from exc
        raise
    with opened as pdf:
        for i, page in enumerate(pdf.pages, 1):
            try:
                out.append((i, page.extract_words()))
            except Exception:
                out.append((i, []))
    return out


# The positional furniture rule. Both constants are measured, not tunable:
# a sweep of grid {2,4,8} pt x share {0.25,0.35,0.5,0.7} over four documents
# moved the excluded share by at most 0.7 points, so they are not flags.
_FURNITURE_GRID = 4.0          # pt cell the (x0, top) key is quantised into
_FURNITURE_PAGE_SHARE = 0.35   # ... repeating on this share of pages (min 3)
_FURNITURE_REFUSE_SHARE = 0.15  # ... above this much of the document: refuse
_LINE_TOLERANCE = 2.0          # pt: words within this much share a line


def _word_key(word: dict) -> tuple:
    """What makes two word instances "the same thing in the same place"."""
    return (_DIGITS.sub("#", word["text"].lower()),
            int(word["x0"] // _FURNITURE_GRID),
            int(word["top"] // _FURNITURE_GRID))


def _lines_from_words(words: list) -> str:
    """Regroup words into text lines by ``top``.

    Tokenising a bag of words would silently disable ``dehyphenate``, which
    only fires at a line end; the report would then count every hyphenated
    word as two losses.
    """
    lines: list[list] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and w["top"] - lines[-1][0] <= _LINE_TOLERANCE:
            lines[-1][1].append(w)
        else:
            lines.append([w["top"], [w]])
    return "\n".join(" ".join(x["text"] for x in sorted(ws, key=lambda w: w["x0"]))
                      for _, ws in lines)


def _word_furniture(pages_words: list) -> tuple[set, int, int]:
    """Word *instances* that repeat in the same place on many pages.

    Reading order is not position. On a three-column sheet the running header
    can sit in the left margin at reading-order indices 2-4, where the
    edge-line rule below cannot see it, and ``extract_text`` welds most of it
    into body lines so no whole line repeats either: a measured document with
    a four-line header on 19 of its 20 pages scored *zero* line patterns.
    Keying on quantised ``(x0, top)`` instead finds it.

    Exclusion is per instance and never per word type -- "with" keeps its body
    occurrences and loses only the ones printed in the header's slot, which a
    vocabulary rule structurally cannot do.
    """
    key_pages: dict = collections.defaultdict(set)
    instances = 0
    for number, words in pages_words:
        instances += len(words)
        for w in words:
            key_pages[_word_key(w)].add(number)
    threshold = max(3, len(pages_words) * _FURNITURE_PAGE_SHARE)
    keys = {k for k, hits in key_pages.items() if len(hits) >= threshold}
    excluded = sum(1 for _, words in pages_words
                   for w in words if _word_key(w) in keys)
    return keys, excluded, instances


def _pdf_pages(source: Path, password, *, warn: bool = True) -> tuple[list, dict]:
    """``[(page, full_text, body_text)]`` plus the furniture report keys.

    ``warn`` gates the ONE line this module prints on stderr. It is a keyword
    with a loud default so every caller stays loud by accident; ``main`` turns
    it off for exactly one reason, ``--json-errors`` (see below).
    """
    pages_words = _page_words(source, password)
    keys, excluded, instances = _word_furniture(pages_words)
    # The guard is a share of the *sheet* -- every word instance the rule
    # would take, whether or not it is long enough to tokenise -- because the
    # question it answers is "how much of this document am I about to delete".
    refused = excluded > instances * _FURNITURE_REFUSE_SHARE
    if refused and warn:
        # A loud no-op, never a silent amputation: something about this
        # document breaks the rule's assumption, and removing a sixth of it
        # on that basis would be worse than reporting furniture as loss.
        #
        # `warn` is what keeps that loudness from breaking a different
        # promise. Under `--json-errors` stderr carries ONE JSON line and
        # nothing else, and a run that printed this and then tripped
        # `--max-loss` put the warning above the envelope, so stderr no longer
        # parsed as JSON at all. The fact is not lost: it is in the report as
        # `furniture_refused`, and `_render` states it in full.
        print(f"furniture detection refused: word-positional rule would "
              f"remove {100.0 * excluded / max(instances, 1):.1f}% of the "
              f"document; falling back to no exclusion", file=sys.stderr)
    out: list[tuple] = []
    vocabulary: collections.Counter = collections.Counter()
    for number, words in pages_words:
        full = _lines_from_words(words)
        if refused or not keys:
            out.append((number, full, full))
            continue
        body, furniture = [], []
        for w in words:
            (furniture if _word_key(w) in keys else body).append(w)
        vocabulary.update(tokens(" ".join(w["text"] for w in furniture)))
        out.append((number, full, _lines_from_words(body)))
    return out, {
        "furniture_patterns": 0 if refused else len(keys),
        "furniture_vocabulary": sorted(vocabulary),
        # Tokens, not raw word instances: the same unit as the dump path
        # below and as ``pdf_tokens`` / ``missing_tokens``, so the three can
        # be compared. Words too short to tokenise ("of", "&", "7/18") are
        # excluded from the comparison all the same -- they just cost it
        # nothing, so counting them here would only inflate the number.
        "furniture_tokens": sum(vocabulary.values()),
        "furniture_granularity": "word",
        "furniture_refused": refused,
        "reference_source": "pdf-words",
    }


_EDGE_HEAD = 2      # lines at the top of a page that may be a running header
_EDGE_TAIL = 3      # ... and at the bottom, a running footer


def _edge_lines(text: str):
    """The lines that can be running furniture: the page's top and bottom.

    ``extract_text`` emits in reading order, so position in the string is a
    usable proxy for position on the sheet when the dump carries no geometry.
    Restricting detection to the edges is what makes a low repetition
    threshold safe -- prose does not repeat there.
    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    # On a sparse page (a part-title sheet) the bands would otherwise cover
    # everything, letting a repetition rule reach real content.
    if len(lines) <= _EDGE_HEAD + _EDGE_TAIL:
        head, tail = lines[:1], lines[-1:]
    else:
        head, tail = lines[:_EDGE_HEAD], lines[-_EDGE_TAIL:]
    return head + [l for l in tail if l not in head]


def _furniture(pages) -> tuple[set, set]:
    """Running headers and footers, as whole-line patterns AND as vocabulary.

    Whole-line matching alone is not enough: a footer that names the current
    chapter ("Generic Options PUBLIC 7") is a *different* line in every
    chapter, so each variant repeats on too few pages to clear any threshold,
    and a measured document leaked ~1600 furniture tokens into the report that
    way. The second signal catches those: a word that turns up in an edge line
    on a large share of pages belongs to the furniture, whatever the rest of
    the line says.
    """
    line_pages: dict = collections.defaultdict(set)
    token_pages: dict = collections.defaultdict(set)
    for number, text in pages:
        for line in _edge_lines(text):
            if len(line) > 90:
                continue
            line_pages[_DIGITS.sub("#", line)].add(number)
            for token in tokens(line):
                token_pages[token].add(number)
    total = max(1, len(pages))
    patterns = {p for p, hits in line_pages.items()
                if len(hits) >= max(3, total * 0.08)}
    vocabulary = {t for t, hits in token_pages.items()
                  if len(hits) >= max(3, total * 0.40)}
    return patterns, vocabulary


def _is_furniture(line: str, patterns: set, vocabulary: set) -> bool:
    if _DIGITS.sub("#", line) in patterns:
        return True
    # A long line is content. The vocabulary rule is deliberately blunt (a
    # title word such as "and" can enter it), so it is confined to short
    # edge lines where the blast radius is a few tokens.
    if not vocabulary or len(line) > 90:
        return False
    words = list(tokens(line).elements())
    if not words:
        return True          # a bare page number
    hits = sum(1 for w in words if w in vocabulary)
    return hits >= len(words) * 0.5


def _dump_pages(source: Path) -> tuple[list, dict]:
    """``[(page, full_text, body_text)]`` for a ``pdf_extract.py`` dump.

    A dump written without ``--lines`` carries no geometry at all -- and that
    is exactly the dump ``SKILL.md`` recommends -- so the positional rule is
    unavailable here and the reading-order rule above applies verbatim.

    Reading ``page['lines']`` from a ``--lines`` dump instead was measured and
    rejected: that stream dropped 19 real upright tokens on a three-column
    document that ``page['text']`` keeps, and it inherits whatever
    ``x_tolerance_ratio`` the dump was taken at -- so an extraction *error*
    reads as an improvement in the loss figure. The point of this module is to
    be an independent second opinion; it does not accept the converter's own
    line model as its reference.
    """
    pages = _page_texts(source)
    patterns, vocabulary = _furniture(pages)
    out: list[tuple] = []
    dropped = 0
    for number, text in pages:
        # Only the page's own edge lines are eligible: a furniture word that
        # also occurs in real prose must never subtract that prose.
        edges = set(_edge_lines(text))
        keep = []
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped in edges and _is_furniture(stripped, patterns, vocabulary):
                dropped += sum(tokens(stripped).values())
                continue
            keep.append(line)
        out.append((number, text, "\n".join(keep)))
    return out, {
        "furniture_patterns": len(patterns),
        "furniture_vocabulary": sorted(vocabulary),
        "furniture_tokens": dropped,
        "furniture_granularity": "line-reading-order",
        "furniture_refused": False,
        "reference_source": "dump-text",
    }


def _is_toc(text: str) -> bool:
    lines = [l for l in text.split("\n") if l.strip()]
    if not lines:
        return False
    return sum(1 for l in lines if _DOTS.search(l)) >= max(3, len(lines) * 0.4)


def verify(source: Path, markdown: Path, *, password=None, top=25,
           warn: bool = True) -> dict:
    """Score `markdown` against `source`, or raise `_SourceRefused`.

    Raises rather than returns whenever the REFERENCE cannot carry a verdict:
    a SOURCE that is not a dump, a dump of no pages, an encrypted PDF, or any
    reference that tokenises to nothing. Returning a report for those scored
    `missing 0 (0.0%)` and passed `--max-loss 0` -- the gate certifying a
    Markdown file it had never compared against anything.
    """
    md_tokens = tokens(strip_markdown(markdown.read_text(encoding="utf-8")))
    if source.suffix.lower() == ".json":
        pages, furniture = _dump_pages(source)
    else:
        pages, furniture = _pdf_pages(source, password, warn=warn)
    pdf_tokens: collections.Counter = collections.Counter()
    per_page: list[tuple] = []
    skipped: list[int] = []
    for number, full, body in pages:
        if _is_toc(full):
            skipped.append(number)
            continue
        page_tokens = tokens(body)
        pdf_tokens.update(page_tokens)
        total = sum(page_tokens.values())
        if total >= 20:
            lost = sum(max(0, n - md_tokens.get(w, 0)) for w, n in page_tokens.items())
            per_page.append((round(lost / total, 3), number, lost, total))
    missing = collections.Counter()
    for word, count in pdf_tokens.items():
        gap = count - md_tokens.get(word, 0)
        if gap > 0:
            missing[word] = gap
    total = sum(pdf_tokens.values())
    if total == 0:
        # `lost / max(total, 1)` below is 0.0 for an empty reference, which is
        # the arithmetic of "nothing is missing" applied to "there was nothing
        # to miss". Every way a reference reaches zero is a reason to stop:
        # a whole-document scan (pdf_extract.py exits 10 and still writes the
        # dump), a dump of a PDF with no text layer, or a document whose every
        # page was skipped as a contents page. Same posture as the furniture
        # refusal -- say so, do not score it.
        raise _SourceRefused(
            f"{source} yielded 0 comparable tokens ({furniture['reference_source']}"
            f", {len(pages)} page(s), {len(skipped)} skipped as contents), so "
            f"there is nothing to check {markdown} against. A scanned or "
            f"text-free PDF needs OCR (pdf_ocr.py) before this gate can mean "
            f"anything.",
            error_type="EmptyReference",
            details={"path": str(source), "pages": len(pages),
                     "toc_pages_skipped": len(skipped)})
    lost = sum(missing.values())
    per_page.sort(reverse=True)
    return {
        "source": str(source),
        "markdown": str(markdown),
        "pdf_tokens": total,
        "md_tokens": sum(md_tokens.values()),
        "missing_tokens": lost,
        "loss_pct": round(100.0 * lost / max(total, 1), 2),
        "toc_pages_skipped": skipped,
        # The vocabulary is deliberately NOT truncated here: at word
        # granularity it is the audit artefact -- the only defence against the
        # one over-fire the measurements cannot rule out (a table header or a
        # slide title repeated in a fixed slot on >=35% of pages).
        **furniture,
        "top_missing": missing.most_common(top),
        "worst_pages": [{"page": n, "loss_pct": round(r * 100, 1),
                         "missing": m, "tokens": t}
                        for r, n, m, t in per_page[:top]],
        "pages_over_25pct": sum(1 for r, _, _, _ in per_page if r > 0.25),
    }


def _render(report: dict) -> str:
    vocabulary = report["furniture_vocabulary"]
    shown = ", ".join(vocabulary[:12])
    if len(vocabulary) > 12:
        shown += f" (+{len(vocabulary) - 12} more, see --json)"
    if report["furniture_refused"]:
        furniture = ("furniture: REFUSED -- the word-positional rule would "
                     "have removed over "
                     f"{int(_FURNITURE_REFUSE_SHARE * 100)}% of the document; "
                     "nothing excluded, so furniture is counted as loss below")
    else:
        # Say what the unit of removal was: the word rule takes one word
        # instance at a time (so "with" keeps its body occurrences), the
        # reading-order rule can only take a whole line.
        per = "instance" if report["furniture_granularity"] == "word" else "line"
        furniture = (f"furniture: {report['furniture_tokens']} token(s) "
                     f"excluded per {per} via {report['furniture_patterns']} "
                     f"{report['furniture_granularity']} pattern(s), "
                     f"vocabulary [{shown}]")
    L = [f"# Coverage: {Path(report['markdown']).name}"
         f"  <-  {Path(report['source']).name}",
         f"  PDF tokens {report['pdf_tokens']} (reference: "
         f"{report['reference_source']}), missing {report['missing_tokens']} "
         f"({report['loss_pct']}%)",
         f"  {furniture}; "
         f"contents pages skipped: {report['toc_pages_skipped'] or 'none'}",
         f"  pages losing >25%: {report['pages_over_25pct']}"]
    if report["worst_pages"]:
        L.append("")
        L.append("## Worst pages")
        for p in report["worst_pages"]:
            L.append(f"  page {str(p['page']).rjust(4)}  {str(p['loss_pct']).rjust(5)}%  "
                     f"({p['missing']}/{p['tokens']} tokens)")
    if report["top_missing"]:
        L.append("")
        L.append("## Most-missing tokens")
        L.append("  (repeated table headers a stitched table emits once are "
                 "expected here)")
        L.append("  " + ", ".join(f"{w} x{n}" for w, n in report["top_missing"]))
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: parse → verify → emit → return the exit code.

    Exit codes: ``0`` checked (and within ``--max-loss`` if given); ``1``
    ``InputNotFound`` / ``NotADump`` / ``EmptyReference`` / ``EncryptedPDF`` /
    ``VerifyFailed`` / ``CoverageBelowThreshold`` / ``StdoutBrokenPipe``;
    ``2`` usage.

    ``install_human_channel`` is called with NO arguments on purpose. The
    two-argument form reconfigures the same two streams but skips the
    ``_quiet_a_dead_stdout`` atexit hook, which is the half of the contract
    that keeps a dead reader (``... | head -1``) from having the interpreter's
    shutdown flush replace this function's exit code with 120.
    """
    install_human_channel()
    args = _build_parser().parse_args(argv)
    for path in (args.SOURCE, args.MARKDOWN):
        if not path.exists():
            return report_error(f"Not found: {path}", code=1,
                                error_type="InputNotFound",
                                json_mode=args.json_errors)
    try:
        # `--json-errors` promises stderr is ONE JSON line: the furniture
        # refusal is withheld from stderr there and read from the report
        # instead (`furniture_refused`, and `_render`'s "furniture: REFUSED").
        report = verify(args.SOURCE, args.MARKDOWN,
                        password=args.password, top=args.top,
                        warn=not args.json_errors)
    except _SourceRefused as exc:
        # A reference that cannot carry a verdict is a refusal with its own
        # `type`, not a generic failure and never a pass: this is the gate the
        # whole toolchain is accepted on.
        return report_error(str(exc), code=1, error_type=exc.error_type,
                            details=exc.details, json_mode=args.json_errors)
    except Exception as exc:
        return report_error(
            f"Verification failed: {type(exc).__name__}: {exc}", code=1,
            error_type="VerifyFailed", json_mode=args.json_errors)
    try:
        if args.json:
            write_json_stdout(report, indent=2)
        else:
            write_text_stdout(_render(report) + "\n")
    except BrokenPipeError:
        # `... | head -1` on a report larger than the pipe buffer. The writer
        # has already pointed fd 1 at /dev/null (`_errors.abandon_stdout`), so
        # what is left is to say it in the envelope rather than let a raw
        # traceback out of a tool whose whole job is a machine-readable
        # verdict.
        return report_error("stdout closed before the report was written",
                            code=1, error_type="StdoutBrokenPipe",
                            details={"stream": "stdout"},
                            json_mode=args.json_errors)
    if args.max_loss is not None and report["loss_pct"] > args.max_loss:
        return report_error(
            f"Coverage below threshold: {report['loss_pct']}% of tokens "
            f"missing, limit {args.max_loss}%", code=1,
            error_type="CoverageBelowThreshold",
            details={"loss_pct": report["loss_pct"], "max_loss": args.max_loss},
            json_mode=args.json_errors)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
