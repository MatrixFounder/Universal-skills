#!/usr/bin/env python3
"""Instrument battery for the text-humanizer eval set. Spends ZERO tokens.

A green run says the INSTRUMENT works. It says nothing about the skill: only a
campaign — `run_humanize.py`, which spawns agents — produces evidence about
what the skill does to a text.

`run_humanize.spawn` is replaced with a sentinel that raises, and TC-EV-29
asserts the sentinel was never reached. This is the step wired into CI.

`EXPECTED_CASES` is a literal here, and TC-EV-44 reads the same number out of
`README.md`. A dropped case is then a red run rather than a smaller
self-consistent total, and a README that still advertises the old count is a
red run rather than a quiet lie.

Exit codes
  0  every case passed
  1  at least one case failed
"""

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import contextlib
import collections

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
sys.path.insert(0, HERE)

import grade_run                                              # noqa: E402
import lexicon                                                # noqa: E402
import run_humanize                                           # noqa: E402

EXPECTED_CASES = 89

# Layout. Every campaign lives under `runs/` (behaviour) or `trigger/runs/`
# (routing), one directory or file per campaign, because guide section 7.2 says a
# new version is a NEW file rather than an overwrite. These four names are the
# only paths the battery knows; moving a campaign means editing them here and
# nowhere else.
# The pin follows the CURRENT skill. It moved from the 2026-09-02 campaign
# when the mode-deliverable fix changed the assembled prompt and made that
# campaign stale by the provenance check. The old campaign is kept, not
# deleted -- it is the evidence under the R2-R6 comparisons.
PINNED_CORPUS = os.path.join("runs", "2026-09-04-full-corpus")
PINNED_REPORT = os.path.join("runs", "2026-09-04-full-report.json")
TRIGGER_SET = os.path.join("trigger", "evals.json")
TRIGGER_TRAIN = os.path.join("trigger", "train.json")
TRIGGER_TEST = os.path.join("trigger", "test.json")

_RESULTS = []


class SpawnReached(AssertionError):
    """The battery called the token-spending path. It must not."""


def _sentinel(*_a, **_kw):
    raise SpawnReached("run_humanize.spawn was called by the battery")


run_humanize.spawn = _sentinel


def case(cid, description):
    def wrap(fn):
        def run():
            try:
                fn()
                _RESULTS.append((cid, description, None))
            except Exception as exc:                          # noqa: BLE001
                _RESULTS.append((cid, description, f"{type(exc).__name__}: {exc}"))
        run.cid = cid
        return run
    return wrap


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _evals():
    return json.loads(_read(os.path.join(HERE, "evals.json")))


def _patterns_text():
    return _read(os.path.join(SKILL, "references", "patterns_universal.md"))


def _quiet(fn, *a, **kw):
    """Call *fn*, swallowing stdout/stderr, and return (rc, out, err)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        rc = fn(*a, **kw)
    return rc, out.getvalue(), err.getvalue()


def _key(case_entry):
    return json.loads(_read(os.path.join(HERE, case_entry["key"])))


def _fixture(case_entry):
    return _read(os.path.join(HERE, case_entry["fixture"]))


# --- schema and configuration --------------------------------------------- #

@case("TC-EV-01", "evals.json declares its schema and all four axes")
def tc01():
    """Four axes, and each answers a different question.

    `failure_mode` — does the skill beat no skill on a planted defect.
    `coverage`     — does it behave correctly on a genre or a style.
    `pressure`     — does it hold its own doctrine when the user leans on it
                     (guide section 6.4). Carries a per-case task file.
    `natural`      — does it behave on prose nobody wrote for this harness
                     (guide section 6.5). Fixture copied verbatim from a
                     repository file the key names.
    """
    ev = _evals()
    assert ev["schema"] == "humanizer-evals/v2", ev["schema"]
    axes = collections.Counter(c["axis"] for c in ev["cases"])
    assert set(axes) == {"failure_mode", "coverage", "pressure", "natural"}, axes
    assert axes["failure_mode"] == 4 and axes["coverage"] == 11, axes
    assert axes["pressure"] >= 3, f"guide 6.4 asks 3+ pressure scenarios, got {axes['pressure']}"
    assert axes["natural"] >= 2, axes
    assert len(ev["cases"]) == 21, len(ev["cases"])


@case("TC-EV-02", "every fixture and key named by a case exists")
def tc02():
    for c in _evals()["cases"]:
        for field in ("fixture", "key"):
            path = os.path.join(HERE, c[field])
            assert os.path.isfile(path), f"{c['id']}: missing {path}"


@case("TC-EV-03", "every key carries must_keep and must_drop as lists")
def tc03():
    for c in _evals()["cases"]:
        k = grade_run._load_key(os.path.join(HERE, c["key"]))
        assert isinstance(k["must_keep"], list)
        assert isinstance(k["must_drop"], list)


@case("TC-EV-04", "every case names a genre humanizer.py accepts")
def tc04():
    sys.path.insert(0, os.path.join(SKILL, "scripts"))
    import humanizer                                          # noqa: PLC0415
    for c in _evals()["cases"]:
        assert c["genre"] in humanizer.GENRE_MAP, c["genre"]


@case("TC-EV-05", "intensity_resolved matches what humanizer.py resolves")
def tc05():
    sys.path.insert(0, os.path.join(SKILL, "scripts"))
    import humanizer                                          # noqa: PLC0415
    for c in _evals()["cases"]:
        actual = humanizer.INTENSITY_DEFAULTS[c["genre"]]
        assert actual == c["intensity_resolved"], \
            f"{c['id']}: declares {c['intensity_resolved']}, resolves {actual}"


@case("TC-EV-06", "the failure-mode cases cover four distinct genres")
def tc06():
    genres = [c["genre"] for c in _evals()["cases"]
              if c["axis"] == "failure_mode"]
    assert len(set(genres)) == 4, genres


@case("TC-EV-07", "exactly one case is the control")
def tc07():
    controls = [c for c in _evals()["cases"] if c.get("control")]
    assert len(controls) == 1, [c["id"] for c in controls]


# --- the arms differ in exactly one input --------------------------------- #

@case("TC-EV-08", "removing the skill block from with_skill gives the baseline byte for byte")
def tc08():
    text = "a text"
    skill_prompt = "SKILL PROMPT BODY"
    base = run_humanize.build_prompt(text, "baseline")
    withs = run_humanize.build_prompt(text, "with_skill", skill_prompt)
    block = run_humanize.skill_block(skill_prompt)
    assert withs.startswith(block), "with_skill does not open with the block"
    assert withs[len(block):] == base, "the arms differ by more than the block"


@case("TC-EV-09", "no task template names a marker, pattern number or rule")
def tc09():
    """Contamination guard, run over EVERY template a case can use.

    A pressure case (guide section 6.4) overrides the shared task so the
    pressure reaches both arms. That override is prose the author wrote, so it
    is the likeliest place for the skill's own doctrine to leak into the
    baseline arm -- at which point the two arms stop differing by one input and
    the case measures nothing.
    """
    roster = lexicon.build()
    derived = [d["term"] for d in roster if d["source"] == "derived"]
    templates = {"<default>": run_humanize.TASK}
    for c in _evals()["cases"]:
        if c.get("task"):
            templates[c["task"]] = _read(os.path.join(HERE, c["task"]))
    assert len(templates) >= 1
    for name, template in templates.items():
        task = template.lower()
        named = [term for term in derived if term.lower() in task]
        assert not named, f"{name} names {named}; both arms would carry the skill"
        for word in ("pattern", "priority", "traffic-light", "intensity",
                     "em dash", "marker"):
            assert word not in task, f"{name} names {word!r}"
        assert "{text}" in template, f"{name} has no fixture slot"


@case("TC-EV-09b", "a per-case task still leaves the arms differing by one input")
def tc09b():
    """The pressure must reach BOTH arms. If an override were applied to
    `with_skill` only, the case would measure the pressure and the skill at
    once and separate neither."""
    for c in _evals()["cases"]:
        template = run_humanize.load_task(c)
        base = run_humanize.build_prompt("FIXTURE", "baseline",
                                         task_template=template)
        withs = run_humanize.build_prompt("FIXTURE", "with_skill", "SKILL",
                                          task_template=template)
        block = run_humanize.skill_block("SKILL")
        assert withs.startswith(block), c["id"]
        assert withs[len(block):] == base, f"{c['id']}: arms differ by more than the block"
        assert "FIXTURE" in base, c["id"]


@case("TC-EV-09c", "a task file a case names must exist and carry the slot")
def tc09c():
    for c in _evals()["cases"]:
        rel = c.get("task")
        if not rel:
            continue
        path = os.path.join(HERE, rel)
        assert os.path.isfile(path), f"{c['id']}: no task file at {rel}"
        assert "{text}" in _read(path), f"{rel}: no {{text}} slot"
    bad = {"id": "X", "task": "tasks/does-not-exist.md"}
    try:
        run_humanize.load_task(bad)
    except (FileNotFoundError, OSError):
        return
    raise AssertionError("a missing task file was accepted")


@case("TC-EV-10", "build_prompt rejects an unknown arm")
def tc10():
    try:
        run_humanize.build_prompt("x", "sideways")
    except ValueError:
        return
    raise AssertionError("an unknown arm was accepted")


@case("TC-EV-11", "with_skill without an assembled prompt is refused")
def tc11():
    try:
        run_humanize.build_prompt("x", "with_skill")
    except ValueError:
        return
    raise AssertionError("with_skill was built with no skill prompt")


@case("TC-EV-12", "the fixture text reaches the prompt verbatim")
def tc12():
    text = _fixture(_evals()["cases"][0])
    assert text in run_humanize.build_prompt(text, "baseline")


# --- the lexicon is derived, not restated --------------------------------- #

@case("TC-EV-13", "a word added to patterns_universal.md reaches the lexicon")
def tc13():
    text = _patterns_text()
    before = lexicon.vocabulary(text)
    edited = text.replace("*   **Adverbs:** undoubtedly,",
                          "*   **Adverbs:** zzqqmarker, undoubtedly,", 1)
    assert edited != text, "the anchor line moved; this case needs re-pinning"
    after = lexicon.vocabulary(edited)
    assert "zzqqmarker" in after and "zzqqmarker" not in before


@case("TC-EV-14", "a word removed from patterns_universal.md leaves the lexicon")
def tc14():
    text = _patterns_text()
    assert "delve" in lexicon.vocabulary(text)
    edited = text.replace("delve, underscore,", "underscore,", 1)
    assert "delve" not in lexicon.vocabulary(edited)


@case("TC-EV-15", "a parenthetical qualifier is stripped from a derived word")
def tc15():
    vocab = lexicon.vocabulary()
    assert "landscape" in vocab, vocab
    assert not any("(" in w for w in vocab), [w for w in vocab if "(" in w]


@case("TC-EV-16", "pattern 1 parsing to nothing is an EmptyClass, not a clean zero")
def tc16():
    text = re.sub(r"^## 1\..*?(?=^## 2\.)", "", _patterns_text(),
                  flags=re.S | re.M)
    try:
        lexicon.build(text)
    except lexicon.EmptyClass:
        return
    raise AssertionError("a vanished pattern 1 produced a live roster")


@case("TC-EV-17", "pattern 10 parsing to nothing is an EmptyClass")
def tc17():
    # The whole `*AI:*` LINE goes. Blanking its first quoted phrase leaves the
    # other three and the class stays live — which is what the first draft of
    # this case did, and it passed while proving nothing.
    text = re.sub(r"^\*\s+\*AI:\*.*$", "*   *AI:* none",
                  _patterns_text(), flags=re.M)
    try:
        lexicon.build(text)
    except lexicon.EmptyClass:
        return
    raise AssertionError("a vanished pattern 10 produced a live roster")


@case("TC-EV-18", "a detector that misses its probe is rejected at build")
def tc18():
    saved = lexicon.NEGATIVE_PARALLELISM
    try:
        lexicon.NEGATIVE_PARALLELISM = re.compile("ZZZ_NEVER_MATCHES")
        try:
            lexicon.build()
        except lexicon.DeadDetector as exc:
            assert "not just" in str(exc), str(exc)
            return
        raise AssertionError("a dead detector produced a live roster")
    finally:
        lexicon.NEGATIVE_PARALLELISM = saved


@case("TC-EV-19", "each authored detector carries more than one probe")
def tc19():
    for det in lexicon.build():
        if det["source"] != "authored":
            continue
        probes = det.get("probes") or []
        assert len(probes) >= 2, f"{det['term']} carries {len(probes)} probe(s)"


@case("TC-EV-20", "negative parallelism fires on the dash form, not only the semicolon")
def tc20():
    rx = lexicon.NEGATIVE_PARALLELISM
    for form in ("It is not just an update — it's a reimagining.",
                 "It's not just a phone; it's a gateway.",
                 "not merely to win, but to dominate"):
        assert rx.search(form), form


@case("TC-EV-21", "ordinary English is not reported as negative parallelism")
def tc21():
    for form in ("We do not just ship on Fridays.",
                 "This is not the release you wanted."):
        assert not lexicon.NEGATIVE_PARALLELISM.search(form), form


@case("TC-EV-22", "every derived word occurs in the shipped reference file")
def tc22():
    text = _patterns_text().lower()
    for word in lexicon.vocabulary():
        assert word in text, word


@case("TC-EV-23", "the roster reports which half each detector came from")
def tc23():
    sources = {d["source"] for d in lexicon.build()}
    assert sources == {"derived", "authored"}, sources


# --- the fixtures and their keys agree ------------------------------------ #

@case("TC-EV-24", "the control fixture carries zero [A] markers")
def tc24():
    control = [c for c in _evals()["cases"] if c.get("control")][0]
    n = lexicon.count(_fixture(control))["total"]
    assert n == 0, f"{control['id']} carries {n} markers"


@case("TC-EV-25", "every non-control fixture carries at least one [A] marker")
def tc25():
    for c in _evals()["cases"]:
        if c.get("control"):
            continue
        n = lexicon.count(_fixture(c))["total"]
        assert n > 0, f"{c['id']} carries none; it measures no removal"


@case("TC-EV-26", "every must_keep anchor is present in its own fixture")
def tc26():
    for c in _evals()["cases"]:
        text = _fixture(c)
        for anchor in _key(c)["must_keep"]:
            # A list anchor must carry its CANONICAL form first, and that form
            # is the one the fixture holds. An anchor whose fixture form is an
            # alternative would grade a text nobody wrote.
            canonical = anchor[0] if isinstance(anchor, list) else anchor
            assert grade_run._present(canonical, text), f"{c['id']}: {canonical!r}"


@case("TC-EV-27", "every must_drop surface is present in its own fixture")
def tc27():
    for c in _evals()["cases"]:
        text = _fixture(c)
        for surface in _key(c)["must_drop"]:
            assert grade_run._present(surface, text), \
                f"{c['id']}: {surface!r} is declared but absent; it grades nothing"


@case("TC-EV-28", "the technical fixture's [A] hits are the declared terms")
def tc28():
    case_entry = [c for c in _evals()["cases"] if c["id"] == "E2"][0]
    hits = {h["term"] for h in lexicon.count(_fixture(case_entry))["hits"]}
    for term in ("dynamic", "robust", "align"):
        assert term in hits, f"{term} no longer fires; E2 measures no false positive"


# --- the executor spends nothing ------------------------------------------ #

@case("TC-EV-29", "the token-spending path was never reached")
def tc29():
    assert run_humanize.spawn is _sentinel, "the sentinel was replaced"


@case("TC-EV-30", "plan_runs honours the arms each case declares")
def tc30():
    ev = _evals()
    runs = run_humanize.plan_runs(ev)
    expected = sum(len(c["arms"]) for c in ev["cases"])
    assert len(runs) == expected, (len(runs), expected)
    assert {r[2] for r in runs} == set(run_humanize.ARMS)
    for label, case, arm, _rep in runs:
        assert arm in case["arms"], label


@case("TC-EV-31", "--cases narrows the plan")
def tc31():
    runs = run_humanize.plan_runs(_evals(), cases=["E2"])
    assert {r[1]["id"] for r in runs} == {"E2"}, runs


@case("TC-EV-32", "--arm narrows the plan")
def tc32():
    runs = run_humanize.plan_runs(_evals(), arms=["with_skill"])
    assert {r[2] for r in runs} == {"with_skill"}


@case("TC-EV-33", "an even --reps is a usage error")
def tc33():
    rc, _, _ = _quiet(run_humanize.main, ["--reps", "2", "--dry-run"])
    assert rc == 3, rc


@case("TC-EV-34", "--jobs 0 is a usage error")
def tc34():
    rc, _, _ = _quiet(run_humanize.main, ["--jobs", "0", "--dry-run"])
    assert rc == 3, rc


@case("TC-EV-35", "a missing eval file is a usage error, not a crash")
def tc35():
    rc, _, _ = _quiet(run_humanize.main, ["--evals", "/nonexistent.json"])
    assert rc == 3, rc


@case("TC-EV-36", "a dry run reaches no agent and exits 0")
def tc36():
    rc, out, _ = _quiet(run_humanize.main, ["--dry-run"])
    assert rc == 0, rc
    expected = sum(len(c["arms"]) for c in _evals()["cases"])
    assert out.count("[dry-run]") == expected, out


@case("TC-EV-37", "the command pins the model and denies every tool")
def tc37():
    argv = run_humanize.build_command("p", "claude-sonnet-5")
    assert argv[:2] == ["claude", "-p"]
    assert "--model" in argv and "claude-sonnet-5" in argv
    for tool in ("Read", "Bash", "Skill", "WebFetch"):
        assert tool in argv, tool


@case("TC-EV-38", "leaks_above finds a context file above the working directory")
def tc38():
    base = tempfile.mkdtemp(prefix="humanizer-leak-")
    try:
        open(os.path.join(base, "CLAUDE.md"), "w", encoding="utf-8").close()
        inner = os.path.join(base, "inner")
        os.makedirs(inner)
        found = run_humanize.leaks_above(inner)
        assert any(f.endswith("CLAUDE.md") for f in found), found
    finally:
        shutil.rmtree(base, ignore_errors=True)


@case("TC-EV-39", "isolated_workdir refuses a leaking parent")
def tc39():
    base = tempfile.mkdtemp(prefix="humanizer-leak-")
    try:
        open(os.path.join(base, "AGENTS.md"), "w", encoding="utf-8").close()
        try:
            run_humanize.isolated_workdir(base=base)
        except run_humanize.NotIsolated:
            return
        raise AssertionError("a leaking parent was accepted")
    finally:
        shutil.rmtree(base, ignore_errors=True)


@case("TC-EV-40", "assemble_skill_prompt calls the shipped script, and intensity reaches it")
def tc40():
    tech = run_humanize.assemble_skill_prompt("technical")
    mkt = run_humanize.assemble_skill_prompt("marketing")
    tags = lambda s: set(re.findall(r"`\[([A-D])\]`", s))
    assert tags(tech) == {"A"}, tags(tech)
    assert tags(mkt) == {"A", "B", "C", "D"}, tags(mkt)


@case("TC-EV-41", "unwrap strips exactly one fence")
def tc41():
    body, did = run_humanize.unwrap("```md\nhello\n```")
    assert did and body == "hello", (did, body)
    body, did = run_humanize.unwrap("hello")
    assert not did and body == "hello"


# --- the grader ----------------------------------------------------------- #

@case("TC-EV-42", "a clean rewrite passes every check on E1")
def tc42():
    c = [x for x in _evals()["cases"] if x["id"] == "E1"][0]
    good = ("Vantage 3.2 is out. Query latency fell from 840 ms to 210 ms on our "
            "internal benchmark. The export pipeline now handles 2.4 million rows "
            "without paging, and SSO works with Okta and Azure AD.")
    r = grade_run.score_run(_fixture(c), good, _key(c), lexicon.build())
    assert r["measured"], r["unmeasured_reason"]
    assert r["checks_passed"] == r["checks_total"], r["checks"]
    assert r["markers_after"] == 0, r["markers_surviving"]


@case("TC-EV-43", "a dropped fact fails facts_kept, and the loss is named")
def tc43():
    c = [x for x in _evals()["cases"] if x["id"] == "E1"][0]
    lossy = ("Vantage 3.2 is out. Query latency fell from 840 ms to 210 ms. The "
             "export pipeline handles 2.4 million rows. SSO works with Okta.")
    r = grade_run.score_run(_fixture(c), lossy, _key(c), lexicon.build())
    failed = [ch for ch in r["checks"] if not ch["passed"]]
    assert [ch["name"] for ch in failed] == ["facts_kept"], r["checks"]
    assert "Azure AD" in r["facts_lost"], r["facts_lost"]


@case("TC-EV-44", "README.md advertises the case count this battery actually runs")
def tc44():
    text = _read(os.path.join(HERE, "README.md"))
    claimed = re.findall(r"(\d+) cases\.", text)
    assert claimed, "README.md states no case count"
    assert str(EXPECTED_CASES) in claimed, \
        f"README.md says {claimed}, EXPECTED_CASES is {EXPECTED_CASES}"


@case("TC-EV-45", "every genre humanizer.py accepts is covered by a case")
def tc45():
    sys.path.insert(0, os.path.join(SKILL, "scripts"))
    import humanizer                                          # noqa: PLC0415
    covered = {c["genre"] for c in _evals()["cases"]}
    missing = set(humanizer.GENRE_MAP) - covered
    assert not missing, f"no case covers {sorted(missing)}"


@case("TC-EV-46", "every shipped style file is injected by some case")
def tc46():
    sys.path.insert(0, os.path.join(SKILL, "scripts"))
    import humanizer                                          # noqa: PLC0415
    shipped = {p[:-3] for p in os.listdir(
        os.path.join(SKILL, "references", "styles")) if p.endswith(".md")}
    # `--style` falls back to the genre name, so a genre whose name matches a
    # style file injects it without declaring one.
    injected = {c.get("style") or c["genre"] for c in _evals()["cases"]}
    missing = shipped - injected
    assert not missing, f"no case injects styles/{sorted(missing)}.md"


@case("TC-EV-47", "a coverage case runs one arm, a failure-mode case runs both")
def tc47():
    for c in _evals()["cases"]:
        arms = c["arms"]
        if c["axis"] == "coverage":
            assert arms == ["with_skill"], f"{c['id']}: {arms}"
        else:
            assert sorted(arms) == sorted(run_humanize.ARMS), f"{c['id']}: {arms}"


@case("TC-EV-48", "a declared style names a file that ships")
def tc48():
    styles_dir = os.path.join(SKILL, "references", "styles")
    for c in _evals()["cases"]:
        if not c.get("style"):
            continue
        path = os.path.join(styles_dir, c["style"] + ".md")
        assert os.path.isfile(path), f"{c['id']}: no {path}"


@case("TC-EV-49", "a cross combination assembles a different prompt from its genre default")
def tc49():
    cross = [c for c in _evals()["cases"] if c.get("style")]
    assert cross, "no case exercises an explicit --style"
    for c in cross:
        default = run_humanize.assemble_skill_prompt(c["genre"])
        crossed = run_humanize.assemble_skill_prompt(c["genre"], style=c["style"])
        assert crossed != default, \
            f"{c['id']}: --style {c['style']} changed nothing in the prompt"


@case("TC-EV-50", "a list anchor is satisfied by any form, a string anchor by one")
def tc50():
    assert grade_run._present(["40 per week", "40 a week"], "about 40 a week here")
    assert grade_run._present(["40 per week", "40 a week"], "exactly 40 per week")
    assert not grade_run._present(["40 per week", "40 a week"], "40 monthly")
    assert grade_run._present("Northwind Analytics", "Northwind Analytics said")
    assert not grade_run._present("Northwind Analytics", "Northwind said"), \
        "a short name must not satisfy the full-name anchor"


@case("TC-EV-51", "a key using surface alternatives says why in must_keep_notes")
def tc51():
    for c in _evals()["cases"]:
        key = _key(c)
        has_alternatives = any(isinstance(a, list) for a in key["must_keep"])
        if has_alternatives:
            assert key.get("must_keep_notes"), \
                f"{c['id']}: alternatives declared with no justification"


@case("TC-EV-52", "re-grading the committed corpus reproduces the committed report")
def tc52():
    """The pin. `skill-evals_guide.md` section 7.2: without it the metrics drift
    from edit to edit and the file keeps advertising the old numbers."""
    import copy
    committed = json.loads(_read(os.path.join(HERE, PINNED_REPORT)))
    roster = lexicon.build()
    evals = _evals()
    fresh = {"schema": "humanizer-evals-report/v1",
             "detectors": len(roster),
             "cases": grade_run.grade(evals, os.path.join(HERE, PINNED_CORPUS), roster)}
    fresh["summary"] = grade_run.summarise(fresh["cases"])
    # Cost carries the run's own metadata and is copied, not recomputed.
    assert fresh["summary"] == committed["summary"], (
        f"summary drifted:\n  committed {committed['summary']}\n  fresh     {fresh['summary']}")
    assert fresh["detectors"] == committed["detectors"]
    for a, b in zip(fresh["cases"], committed["cases"]):
        assert a["id"] == b["id"]
        for arm in ("baseline", "with_skill"):
            for x, y in zip(a["arms"].get(arm, []), b["arms"].get(arm, [])):
                assert x["checks"] == y["checks"], f"{a['id']}/{arm}: checks drifted"


@case("TC-EV-53", "the fabrication guard fires on an invented figure and not on a restated one")
def tc53():
    src = "Latency fell to 210 ms across twenty runs."
    assert grade_run.invented_numbers(src, "Latency fell to 210 ms in 20 runs.") == []
    assert grade_run.invented_numbers(src, "Latency fell to 210 ms, a 45% gain.") == ["45"]
    assert grade_run.invented_numbers(src, "Latency fell to 99 ms.") == ["99"]


@case("TC-EV-54", "a trigger eval set ships, with positives and near-misses")
def tc54():
    """`skill-evals_guide.md` section 3: trigger and behavior are two independent
    checks. This battery covers behavior; the set below is what feeds the other."""
    path = os.path.join(HERE, TRIGGER_SET)
    assert os.path.isfile(path), f"no {TRIGGER_SET} ships"
    data = json.loads(_read(path))
    assert len(data) >= 30, len(data)
    pos = [q for q in data if q["should_trigger"]]
    neg = [q for q in data if not q["should_trigger"]]
    assert len(pos) >= 18 and len(neg) >= 10, (len(pos), len(neg))
    for q in data:
        assert set(q) == {"query", "should_trigger"}, sorted(q)
        assert q["query"].strip()


@case("TC-EV-55", "train and test halves partition the trigger set, with no overlap")
def tc55():
    """The anti-overfitting invariant, made checkable.

    A description tuned against queries that also grade it is tuned against
    itself (`skill-evals_guide.md` section 5.2). The split is committed, and
    this case fails if a query ever appears in both halves or is dropped from
    both.
    """
    full = json.loads(_read(os.path.join(HERE, TRIGGER_SET)))
    train = json.loads(_read(os.path.join(HERE, TRIGGER_TRAIN)))
    test = json.loads(_read(os.path.join(HERE, TRIGGER_TEST)))
    q = lambda s: {x["query"] for x in s}
    assert not (q(train) & q(test)), sorted(q(train) & q(test))
    assert q(train) | q(test) == q(full), "the split lost or invented a query"
    assert len(test) >= 6 and len(train) >= 15, (len(train), len(test))


@case("TC-EV-56", "both halves carry positives and near-misses")
def tc56():
    """A half with one class only measures one failure mode."""
    for name in (TRIGGER_TRAIN, TRIGGER_TEST):
        data = json.loads(_read(os.path.join(HERE, name)))
        pos = sum(1 for x in data if x["should_trigger"])
        neg = len(data) - pos
        assert pos >= 3 and neg >= 2, f"{name}: {pos} positive, {neg} negative"


@case("TC-EV-57", "every case that can fire an additive rule carries a growth ceiling")
def tc57():
    """R7. The skew is prose in `rewriting_strategy.md`; this is what measures it.

    The boundary is mechanical rather than editorial: only genres mapping to
    `patterns_creative.md` load the additive rules at all, so only those cases
    can breach the skew. A wiki-family case has no ceiling because nothing in
    its prompt could grow it for R7's reason.
    """
    creative = {"blog", "social", "marketing", "corporate", "food", "crypto"}
    for c in _evals()["cases"]:
        key = json.loads(_read(os.path.join(HERE, c["key"])))
        ceiling = key.get("max_growth")
        if c["genre"] in creative:
            assert ceiling, f"{c['id']} ({c['genre']}) can grow and has no ceiling"
            assert "DECLARED, not fitted" in key.get("max_growth_derivation", "") \
                or "DECLARED" in key.get("note", ""), \
                f"{c['id']}: a ceiling with no stated derivation is a fitted number"
        else:
            assert ceiling is None, \
                f"{c['id']} ({c['genre']}) never loads the additive rules"


@case("TC-EV-58", "the recorded corpus is within every ceiling, and says by how much")
def tc58():
    """A ceiling nothing approaches is not a guard, it is decoration. This case
    reports the headroom so a future tightening is an informed edit."""
    report = json.loads(_read(os.path.join(HERE, PINNED_REPORT)))
    seen = 0
    for c in report["cases"]:
        for runs in c["arms"].values():
            for r in runs:
                for ck in r["checks"]:
                    if ck["name"] == "proportionate_length":
                        seen += 1
                        assert ck["passed"], f"{c['id']}: {ck['detail']}"
    assert seen >= 10, f"only {seen} runs were length-checked"


@case("TC-EV-59", "the skew is stated where the intensity throttle cannot remove it")
def tc59():
    """R7 has to reach `low` and `minimal` too -- technical and legal text is
    where an inserted opinion does the most damage, and it is exactly where the
    additive rules are already filtered out, so the skew is the only carrier."""
    refs = os.path.join(os.path.dirname(HERE), "references")
    strategy = _read(os.path.join(refs, "rewriting_strategy.md"))
    assert "Which Operation to Reach For" in strategy
    assert "a skew, not a ban" in strategy, "a ban would flatten flat text further"
    creative = _read(os.path.join(refs, "patterns_creative.md"))
    assert creative.count("**Conditional (additive):**") == 3, \
        "R7 marks exactly three additive rules conditional"


@case("TC-EV-60", "the fiction boundary is stated in the description, not only the body")
def tc60():
    """R8. Routing reads the description; a boundary stated only in the body is
    read after the skill has already been chosen. The two fiction near-misses in
    `trigger_evals.json` are what this claim is measured against."""
    skill = _read(os.path.join(os.path.dirname(HERE), "SKILL.md"))
    description = re.search(r"^description: (.+)$", skill, re.M).group(1)
    low = description.lower()
    # The PROPERTY, not one wording. R8 measured that naming the FORMS is what
    # stopped the novella routing here (1.00 -> 0.00); a later description kept
    # the sentence "not for prose fiction", dropped the forms, and the misroute
    # came back at 0.67 while this case stayed green on the sentence alone.
    assert "non-fiction" in low, "the description does not say it is non-fiction"
    forms = [f for f in ("short story", "novel", "screenplay", "chapter") if f in low]
    assert len(forms) >= 2, (
        f"the description names {forms}; naming the forms is what the R8 "
        f"measurement showed to be load-bearing")
    assert len(description.split()) <= 70, len(description.split())
    fiction = [q for q in json.loads(_read(os.path.join(HERE, TRIGGER_SET)))
               if not q["should_trigger"]
               and re.search(r"рассказ|story|novel|chapter", q["query"], re.I)]
    assert len(fiction) >= 2, f"only {len(fiction)} fiction near-misses to measure against"


@case("TC-EV-61", "the house exporter reproduces every graded run")
def tc61():
    """The schema divergence had a cost: none of the shared tools could read
    this harness. `export_benchmark.py` pays it off by translating. If the
    translation drops runs, the shared view silently under-reports."""
    import export_benchmark                                    # noqa: PLC0415
    report = json.loads(_read(os.path.join(HERE, PINNED_REPORT)))
    expected = sum(len(runs) for c in report["cases"] for runs in c["arms"].values())
    out = os.path.join(tempfile.mkdtemp(prefix="th-export-"), "bench")
    try:
        _report, written, cases = export_benchmark.export(
            os.path.join(HERE, PINNED_REPORT), out)
        assert written == expected, f"exported {written} of {expected} runs"
        assert len(cases) == len(report["cases"])
        for index, c in enumerate(report["cases"], start=1):
            for arm, runs in c["arms"].items():
                config = export_benchmark.ARM_NAMES[arm]
                for rep, run in enumerate(runs, start=1):
                    path = os.path.join(out, f"eval-{index}", config,
                                        f"run-{rep}", "grading.json")
                    assert os.path.isfile(path), path
                    g = json.loads(_read(path))
                    assert g["summary"]["passed"] == run["checks_passed"]
                    assert g["summary"]["total"] == run["checks_total"]
                    assert len(g["expectations"]) == len(run["checks"])
    finally:
        shutil.rmtree(os.path.dirname(out), ignore_errors=True)


@case("TC-EV-62", "the house aggregator and verify_pin both read the export")
def tc62():
    """Runs `skill-creator/scripts/aggregate_benchmark.py` then `verify_pin.py`
    over the translated view. Pure recomputation -- no model, no token."""
    import export_benchmark                                    # noqa: PLC0415
    out = os.path.join(tempfile.mkdtemp(prefix="th-export-"), "bench")
    try:
        export_benchmark.export(os.path.join(HERE, PINNED_REPORT), out,
                                paired_only=True)
        agg = export_benchmark.house("aggregate_benchmark.py", out)
        assert agg.returncode == 0, agg.stderr[-400:]
        benchmark = os.path.join(out, "benchmark.json")
        assert os.path.isfile(benchmark), "aggregate wrote no benchmark.json"
        data = json.loads(_read(benchmark))
        summary = data.get("run_summary") or {}
        assert {"with_skill", "without_skill"} <= set(summary), sorted(summary)
        pin = export_benchmark.house("verify_pin.py", out, benchmark)
        assert pin.returncode == 0, pin.stderr[-400:]
    finally:
        shutil.rmtree(os.path.dirname(out), ignore_errors=True)


@case("TC-EV-63", "an unbalanced export is reported, not quietly averaged")
def tc63():
    """The coverage cases run one arm, so the DEFAULT export is 15 treatment
    cases against 4 baseline ones and `aggregate_benchmark.py` prints a delta
    between two different populations. Guide section 11.2 calls the silent
    version of this an antipattern; the exporter must say so on stderr."""
    import export_benchmark                                    # noqa: PLC0415
    script = os.path.join(HERE, "export_benchmark.py")
    root = tempfile.mkdtemp(prefix="th-export-")
    try:
        full = subprocess.run(
            [sys.executable, script, "--out", os.path.join(root, "all")],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert full.returncode == 0, full.stderr[-300:]
        assert "WARNING" in full.stderr and "compares populations" in full.stderr,             "an unbalanced export printed no warning"
        paired = subprocess.run(
            [sys.executable, script, "--paired-only",
             "--out", os.path.join(root, "paired")],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        assert paired.returncode == 0, paired.stderr[-300:]
        assert "WARNING" not in paired.stderr,             f"a balanced export warned anyway: {paired.stderr[:200]}"
    finally:
        shutil.rmtree(root, ignore_errors=True)


@case("TC-EV-64", "--cases accepts the space-separated form anybody would type")
def tc64():
    """`--cases E1 E2` used to raise "unrecognized arguments: E2". It planned
    nothing and exited 3, so a narrowed re-draw silently ran zero agents."""
    plan_space = run_humanize.plan_runs(_evals(), reps=1, cases=["E1", "E2"])
    assert {r[1]["id"] for r in plan_space} == {"E1", "E2"}, plan_space
    rc, out, err = _quiet(run_humanize.main,
                          ["--cases", "E1", "E2", "--dry-run"])
    assert rc == 0, f"exit {rc}: {err[:200]}"
    assert out.count("[dry-run]") == 4, out
    rc2, out2, _ = _quiet(run_humanize.main,
                          ["--cases", "E1", "--cases", "E2", "--dry-run"])
    assert rc2 == 0 and out2 == out, "the two spellings plan different runs"


@case("TC-EV-65", "a usage error says which flag was wrong")
def tc65():
    """`exit_on_error = False` keeps a bad flag from killing the process, and it
    also moves argparse's message into the exception. An exit 3 that prints
    nothing sends the caller to the source to find out what they mistyped."""
    rc, out, err = _quiet(run_humanize.main, ["--nonsense"])
    assert rc == 3, rc
    assert "usage error" in err and "--nonsense" in err, repr(err[:200])
    rc2, _out2, err2 = _quiet(run_humanize.main, ["--reps", "2"])
    assert rc2 == 3 and "must be odd" in err2, repr(err2[:200])


@case("TC-EV-66", "a multi-rep plan draws every rep of every requested arm")
def tc66():
    """Guide section 7.5: a single draw of a jittery metric cannot separate an
    effect from noise. The plan must actually widen with --reps."""
    ev = _evals()
    one = run_humanize.plan_runs(ev, reps=1, cases=["E1", "E2", "E3", "E4"])
    three = run_humanize.plan_runs(ev, reps=3, cases=["E1", "E2", "E3", "E4"])
    assert len(three) == 3 * len(one), (len(one), len(three))
    assert len(one) == 8, "the four paired cases carry two arms each"
    reps = {r[3] for r in three}
    assert reps == {1, 2, 3}, reps
    assert len({r[0] for r in three}) == len(three), "a run id repeats"


@case("TC-EV-67", "every path README.md names under runs/ or trigger/ exists")
def tc67():
    """The campaigns were re-homed once; the README named the old paths for as
    long as nobody looked. A document pointing at evidence that moved is worse
    than one that points at none, because it reads as checkable."""
    import glob                                                # noqa: PLC0415
    text = _read(os.path.join(HERE, "README.md"))
    named = set(re.findall(r"`((?:runs|trigger|fixtures)/[A-Za-z0-9_.\-*/]*)`",
                           text))
    assert len(named) >= 15, f"only {len(named)} paths found; the regex broke"
    missing = []
    for rel in sorted(named):
        full = os.path.join(HERE, rel)
        if "*" in rel:
            if not glob.glob(full):
                missing.append(rel)
        elif not os.path.exists(full.rstrip("/")):
            missing.append(rel)
    assert not missing, f"README names paths that do not exist: {missing}"


@case("TC-EV-68", "each campaign directory has the report that grades it")
def tc68():
    """A corpus with no report is evidence nobody scored; a report with no
    corpus is a number nobody can re-derive. Guide section 7.2 wants both kept."""
    runs = os.path.join(HERE, "runs")
    corpora = sorted(d for d in os.listdir(runs) if d.endswith("-corpus"))
    assert len(corpora) >= 4, corpora
    for corpus in corpora:
        if corpus.startswith("scratch"):
            continue
        stem = corpus[: -len("-corpus")]
        report = os.path.join(runs, f"{stem}-report.json")
        if stem.endswith("control-x3"):
            continue          # extra draws of one case, folded into another report
        assert os.path.isfile(report), f"{corpus} has no {stem}-report.json"
        data = json.loads(_read(report))
        assert data["cases"], f"{stem}: an empty report"


@case("TC-EV-69", "the authored detectors are probed with the reference file's own examples")
def tc69():
    """The last piece of guide section 7.1 this harness could reach.

    There is no production verdict function to call -- `humanizer.py` assembles a
    prompt and decides nothing -- so the two structural regexes cannot "call
    production logic". What they CAN do is answer to the shipped document: their
    probes are now the quoted `*AI:*` examples parsed out of patterns 3 and 9,
    so an example the regex fails to match is a red battery instead of a silent
    divergence between what the skill tells the model and what the grader counts.
    """
    roster = lexicon.build()
    authored = {d["term"]: d for d in roster if d["source"] == "authored"}
    assert set(authored) == {"not just X, but Y", "em dash"}, sorted(authored)
    for number, term in ((3, "not just X, but Y"), (9, "em dash")):
        with_ = lexicon.examples_for(number)
        assert with_, f"pattern {number} yields no example"
        for example in with_:
            assert example in authored[term]["probes"], \
                f"pattern {number}'s example {example!r} is not probed"
            assert authored[term]["re"].search(example), \
                f"the {term} regex misses the reference file's own example"


@case("TC-EV-70", "an example the regex cannot match turns the battery red")
def tc70():
    """The guard has to actually fire, or it is decoration."""
    text = _patterns_text()
    broken = text.replace(
        '*   *AI:* "It\'s not just a phone; it\'s a gateway to the world."',
        '*   *AI:* "A perfectly ordinary sentence with no structure at all."', 1)
    assert broken != text, "the anchor line moved; this case needs re-pinning"
    try:
        lexicon.build(broken)
    except lexicon.DeadDetector:
        return
    except lexicon.EmptyClass:
        raise AssertionError("raised EmptyClass; the example parse broke instead")
    raise AssertionError("an unmatched reference example was accepted")


@case("TC-EV-71", "a pattern that loses its examples is refused, not silently unprobed")
def tc71():
    text = _patterns_text()
    sec = lexicon.sections(text)[9]
    stripped = text.replace(sec["body"], "\nNo examples here.\n", 1)
    try:
        lexicon.examples_for(9, stripped)
    except lexicon.EmptyClass:
        pass
    else:
        raise AssertionError("a pattern with no quoted example was accepted")
    try:
        lexicon.examples_for(99, text)
    except lexicon.EmptyClass:
        return
    raise AssertionError("a missing pattern number was accepted")


@case("TC-EV-72", "a natural fixture is verbatim in the repository file it names")
def tc72():
    """The guard that a critic lens failed to be.

    A `natural` case exists to remove author bias (guide section 6.5): the point
    is prose NOBODY wrote for this harness. An agent authoring one of these
    copied a real repository passage and then inserted `In summary,` and
    `crucial` into it -- its own notes said the two hits "were placed
    mechanically" -- and three adversarial reviewers, one of them assigned that
    exact check, passed it. A seeded case wearing a natural label is worse than
    an honestly seeded one, because it is quoted as evidence of the thing it is
    not. This is mechanical and does not get tired.
    """
    repo = os.path.abspath(os.path.join(SKILL, "..", ".."))
    natural = [c for c in _evals()["cases"] if c["axis"] == "natural"]
    assert natural, "no natural case ships"
    norm = lambda s: " ".join(s.split())
    for c in natural:
        key = _key(c)
        source = key.get("natural_source")
        assert source, f"{c['id']}: a natural case must name its source file"
        path = os.path.join(repo, source)
        assert os.path.isfile(path), f"{c['id']}: no such source {source}"
        assert "evals" not in source.split(os.sep), \
            f"{c['id']}: {source} is inside the harness; that is not natural prose"
        src = norm(_read(path))
        for para in _fixture(c).strip().split("\n\n"):
            if not para.strip():
                continue
            assert norm(para) in src, \
                (f"{c['id']}: a paragraph is not verbatim in {source} -- "
                 f"{norm(para)[:70]!r}")


@case("TC-EV-73", "a pressure case carries a task file that is not the shared one")
def tc73():
    """A pressure case whose instruction is the default task applies no pressure
    and is a coverage case with a different label."""
    pressure = [c for c in _evals()["cases"] if c["axis"] == "pressure"]
    assert len(pressure) >= 3, f"guide 6.4 asks for 3+, got {len(pressure)}"
    kinds = set()
    for c in pressure:
        assert c.get("task"), f"{c['id']}: a pressure case needs its own task"
        template = _read(os.path.join(HERE, c["task"]))
        assert template != run_humanize.TASK, \
            f"{c['id']}: its task is the shared default; no pressure is applied"
        assert len(template) > len(run_humanize.TASK), \
            f"{c['id']}: the task is shorter than the default; where is the pressure"
        assert c["arms"] == ["baseline", "with_skill"], \
            f"{c['id']}: pressure is a comparison, so it needs both arms"
        kinds.add(_key(c)["note"][:40])
    assert len(kinds) == len(pressure), "two pressure cases share a description"


@case("TC-EV-74", "must_not_appear holds only surfaces absent from the fixture")
def tc74():
    """`must_drop` and `must_not_appear` are opposite intents and the harness has
    to keep them apart. A guard already in the source would pass whatever the run
    did to it; a removal check for something never present passes vacuously."""
    used = 0
    for c in _evals()["cases"]:
        key = _key(c)
        guards = key.get("must_not_appear") or []
        if guards:
            used += 1
            assert key.get("must_not_appear_notes"), \
                f"{c['id']}: guards with no stated intent"
        text = _fixture(c)
        for s in guards:
            assert not grade_run._present(s, text), \
                f"{c['id']}: {s!r} is IN the fixture; that is a must_drop"
    assert used >= 1, "no case uses the reinjection guard"


@case("TC-EV-75", "the reinjection check fires on an added surface and not otherwise")
def tc75():
    roster = lexicon.build()
    key = {"must_keep": ["anchor"], "must_drop": [],
           "must_not_appear": ["Certainly!"], "min_similarity": None,
           "max_growth": None}
    fixture = "An anchor sentence with enough characters to clear the floor. " * 3
    clean = grade_run.score_run(fixture, fixture, key, roster)
    named = {c["name"]: c for c in clean["checks"]}
    assert "no_reinjection" in named, sorted(named)
    assert named["no_reinjection"]["passed"], named["no_reinjection"]
    dirty = grade_run.score_run(fixture, "Certainly! " + fixture, key, roster)
    bad = {c["name"]: c for c in dirty["checks"]}["no_reinjection"]
    assert not bad["passed"], bad
    assert "Certainly!" in bad["detail"], bad["detail"]
    # a key without the field grows no check
    key.pop("must_not_appear")
    none = grade_run.score_run(fixture, fixture, key, roster)
    assert "no_reinjection" not in {c["name"] for c in none["checks"]}


@case("TC-EV-76", "every committed report says truthfully whether it is stale")
def tc76():
    """Guide section 8: an eval goes stale when the skill moves under it, and a
    stale figure that still reads as current is worse than no figure.

    The corpus metadata fingerprints the exact assembled prompt each run saw.
    `provenance()` compares that against what `humanizer.py` assembles today and
    writes the answer into the report. This case asserts the report does not
    LIE: whatever it claims about staleness has to match a fresh computation.
    A non-empty `stale_vs_today` is allowed and is not a failure -- it is the
    report doing its job.
    """
    import glob                                                # noqa: PLC0415
    reports = sorted(glob.glob(os.path.join(HERE, "runs", "*-report.json")))
    assert reports, "no committed report"
    roster = lexicon.build()
    evals = _evals()
    for path in reports:
        committed = json.loads(_read(path))
        prov = committed.get("provenance")
        assert prov, f"{os.path.basename(path)}: no provenance block"
        corpus = os.path.join(HERE, "runs", prov["corpus"])
        assert os.path.isdir(corpus), f"{prov['corpus']} is named but absent"
        fresh = grade_run.provenance(
            grade_run.grade(evals, corpus, roster), corpus, roster)
        assert fresh["stale_vs_today"] == prov["stale_vs_today"], (
            f"{os.path.basename(path)}: the report claims stale="
            f"{prov['stale_vs_today']}, a fresh check says "
            f"{fresh['stale_vs_today']}")
        assert prov["skill_version"], "the report records no skill version"


@case("TC-EV-77", "a moved reference file would change the assembled-prompt hash")
def tc77():
    """The staleness guard has to be able to fire, or it is decoration.

    The direct proof would edit a reference file, re-assemble and compare. This
    battery does NOT do that: it runs while campaigns run, and a file mutated
    for even a moment would be baked into whatever prompt `run_humanize.py`
    assembled in that window -- a test that corrupts the evidence it exists to
    protect. Instead it proves the dependency read-only: the hash is taken over
    the assembled prompt, and the assembled prompt demonstrably carries content
    from each reference file that feeds it. Change any of those files and the
    bytes change, so the hash changes.
    """
    for genre, files in (("marketing", ("patterns_universal.md",
                                        "patterns_creative.md",
                                        "rewriting_strategy.md")),
                         ("technical", ("patterns_universal.md",
                                        "patterns_wiki.md",
                                        "rewriting_strategy.md"))):
        prompt = run_humanize.assemble_skill_prompt(genre)
        for name in files:
            body = _read(os.path.join(SKILL, "references", name))
            # A sentence long enough to be unique to that file, taken from it
            # rather than typed here, so a rewrite of the file moves the probe
            # with it instead of leaving a stale literal behind.
            probes = [l.strip() for l in body.splitlines()
                      if len(l.strip()) > 60 and not l.lstrip().startswith(("#", ">", "|"))]
            assert probes, f"{name}: no line long enough to probe with"
            assert any(pr in prompt for pr in probes[:12]), \
                (f"{genre}: nothing from {name} reached the assembled prompt; "
                 f"the staleness hash would stop tracking it")
        # and the hash is taken over exactly those bytes
        assert run_humanize._sha(prompt) == run_humanize._sha(prompt)
        assert run_humanize._sha(prompt) != run_humanize._sha(prompt + " ")


@case("TC-EV-78", "a returned system prompt is a finding, not a bad rewrite")
def tc78():
    """The 2026-09-03 pressure campaign made a documented hazard real.

    `assets/generator_template.md` opens with "generate a SYSTEM PROMPT" and
    closes with "Output the final System Prompt" -- in EVERY mode, `humanize`
    included. Under a high-pressure brief, three of eighteen `with_skill` runs
    did what that literally asks and returned a prompt instead of the rewritten
    text.

    The anchor floor caught two and MISSED the third, because a generated prompt
    quotes the fixture inside itself: P2/with_skill/rep-1 kept 19 of 19 anchors
    while being six times the source length and carrying 81 markers against the
    source's 13. Graded as a bad edit it dragged the arm's marker total from 23
    to 104 -- a number that would have been quoted as "the skill leaves more
    markers than no skill".
    """
    roster = lexicon.build()
    key = {"must_keep": ["anchor"], "must_drop": [], "min_similarity": None,
           "max_growth": None}
    fixture = "An anchor sentence long enough to clear the character floor. " * 3

    prompt_like = (fixture + "\n\n## 1. Diagnosis\n\nClassify each paragraph "
                   "with a traffic-light system. **Red** (3+ AI markers detected): "
                   "rewrite it. Anti-Pattern List follows.")
    graded = grade_run.score_run(fixture, prompt_like, key, roster)
    assert not graded["measured"], "a returned prompt was graded as a rewrite"
    assert "SYSTEM PROMPT" in graded["unmeasured_reason"], graded["unmeasured_reason"]
    assert len(graded["template_signatures"]) >= grade_run.TEMPLATE_HITS

    # and an ordinary rewrite is untouched by the guard
    clean = grade_run.score_run(fixture, fixture.replace("anchor", "anchor"), key, roster)
    assert clean["measured"], clean["unmeasured_reason"]
    assert clean["template_signatures"] == []


@case("TC-EV-79", "neither a fixture nor a task file trips the prompt detector")
def tc79():
    """A guard that fires on the input would make every run of that case
    unmeasurable, which reads as 'the skill failed' and is not."""
    for c in _evals()["cases"]:
        hits = grade_run.returned_the_prompt(_fixture(c))
        assert len(hits) < grade_run.TEMPLATE_HITS, f"{c['id']} fixture: {hits}"
        if c.get("task"):
            hits = grade_run.returned_the_prompt(
                _read(os.path.join(HERE, c["task"])))
            assert len(hits) < grade_run.TEMPLATE_HITS, f"{c['id']} task: {hits}"


@case("TC-EV-80", "a runaway answer is caught even with no prompt wording")
def tc80():
    """The independent structural net. Wording drifts; a document three times
    the source length carrying three times the markers is not a rewrite of it
    whatever it says."""
    roster = lexicon.build()
    key = {"must_keep": ["delve"], "must_drop": [], "min_similarity": None,
           "max_growth": None}
    fixture = "We delve into the seamless robust result. " * 3
    runaway = fixture + (" It is a testament to the vibrant landscape, "
                         "underscoring a crucial and meticulous journey. " * 12)
    graded = grade_run.score_run(fixture, runaway, key, roster)
    assert not graded["measured"], "a runaway answer was graded as a rewrite"
    assert "different document" in graded["unmeasured_reason"], \
        graded["unmeasured_reason"]
    assert graded["template_signatures"] == [], \
        "this case must exercise the STRUCTURAL net, not the wording one"


@case("TC-EV-81", "a cross-style case is not reported stale for losing its style")
def tc81():
    """Regression. `provenance()` re-assembled today's prompt with
    `case.get("style")` -- but `grade()` does not carry `style`, so it was always
    None. For the eleven cases where --style falls back to the genre name the
    two hashes coincided and nothing showed; for S1-S4, where the style differs
    from the genre, every one reported STALE against a corpus drawn minutes
    earlier. A staleness check that cries wolf is worse than none: the next real
    staleness gets read as the same bug.
    """
    roster = lexicon.build()
    evals = _evals()
    corpus = os.path.join(HERE, PINNED_CORPUS)
    prov = grade_run.provenance(grade_run.grade(evals, corpus, roster),
                                corpus, roster)
    cross = [c["id"] for c in evals["cases"]
             if c.get("style") and c["style"] != c["genre"]]
    assert len(cross) >= 4, f"only {len(cross)} cross-style cases: {cross}"
    falsely = [cid for cid in cross if cid in prov["stale_vs_today"]]
    assert not falsely, (
        f"{falsely} report stale in a corpus drawn against the current skill; "
        f"the style is being dropped when today's prompt is re-assembled")
    assert prov["stale_vs_today"] == [], (
        f"the pinned corpus is stale: {prov['stale_vs_today']}. Re-draw it, or "
        f"move the pin -- a pinned campaign must describe the current skill")


@case("TC-EV-82", "no anchor demands the wording of a claim rather than a fact")
def tc82():
    """The rotten assertion in REVERSE: a check no correct run can pass.

    N1 declared five anchors that quoted a claim's WORDING, one of them twenty
    words spanning two sentences. Every task here asks for the text to be
    rephrased, so those checks were unsatisfiable by construction. Both arms
    lost exactly the same five in every repetition -- the signature of a broken
    key, not of a skill that fails -- and it was read as "the one case the skill
    does not handle" until the outputs were opened by hand.

    The rule: a name, a number or an identifier keeps its exact string, because
    its identity IS the string. A claim's phrasing must offer the forms a
    faithful rewrite may choose.

    A long anchor is legitimate when the text is QUOTED MATERIAL that must
    survive verbatim -- P3's contractual vendor sentence is the case -- so the
    test is sentence-spanning, not length, and a key may name the exemption.
    """
    import re as _re
    offenders = []
    for c in _evals()["cases"]:
        key = _key(c)
        notes = (key.get("must_keep_notes") or "") + (key.get("note") or "")
        for anchor in key["must_keep"]:
            canonical = anchor[0] if isinstance(anchor, list) else anchor
            # A full stop followed by a capital is a sentence boundary. An
            # anchor that spans one is quoting prose, not naming a thing.
            if _re.search(r"[.!?]\s+[A-ZА-Я]", canonical):
                if "quoted material" in notes.lower() or "verbatim" in notes.lower():
                    continue
                offenders.append(f"{c['id']}: {canonical[:60]!r}")
    assert not offenders, (
        "an anchor spans a sentence boundary and its key does not claim the "
        f"quoted-material exemption: {offenders}")


@case("TC-EV-83", "a natural case anchors names, and offers forms for claims")
def tc83():
    """Tighter than TC-EV-82 and only where it must be. A `natural` fixture is
    prose nobody wrote for this harness, so every anchor in it is either
    something whose identity is its string, or a claim that a rewrite may
    legitimately word differently."""
    thin = []
    for c in _evals()["cases"]:
        if c["axis"] != "natural":
            continue
        for anchor in _key(c)["must_keep"]:
            if isinstance(anchor, list):
                continue
            # A bare string anchor must be a name, a number or an identifier
            # rather than a clause. Backticks in the fixture settle it: a
            # code-quoted span is a name however many words it holds, and a
            # rewrite that changed it would be changing an identifier.
            if len(anchor.split()) <= 4:
                continue
            if f"`{anchor}`" in _fixture(c):
                continue
            thin.append(f"{c['id']}: {anchor!r}")
    assert not thin, (
        "a natural case declares a multi-word string anchor with no alternative "
        f"forms; a rewrite that keeps the fact would still fail it: {thin}")


@case("TC-EV-84", "the false-positive sweep reads the shipped word list, not a copy")
def tc84():
    """`[A]` is the only class reaching `low` and `minimal`, and it is a list of
    WORDS rather than meanings, so every entry is a standing false-positive
    risk. The sweep answers "does this word fire on correct usage" from corpora
    already on disk. It must derive its word list from the reference file: a
    restated copy would go stale the first time the list is edited."""
    import false_positive_sweep as fps                          # noqa: PLC0415
    words = fps.vocabulary()
    assert len(words) >= 20, f"only {len(words)} words parsed"
    roster = {d["term"].lower() for d in lexicon.build()
              if d["kind"] == "ai_vocabulary"}
    assert set(words) == roster, "the sweep and the grader disagree on the list"
    # and the list really is parsed, not literal
    source = _read(os.path.join(HERE, "false_positive_sweep.py"))
    for w in ("delve", "seamless", "testament"):
        assert f'"{w}"' not in source, f"{w!r} is hard-coded in the sweep"


@case("TC-EV-85", "the sweep scores only cases carrying both arms")
def tc85():
    """A survival rate with nothing to compare it against says nothing. A
    coverage case runs `with_skill` alone, so it belongs in `unpaired`, and
    counting it as evidence would read the model's own habits as the skill's."""
    import false_positive_sweep as fps                          # noqa: PLC0415
    evals = _evals()
    rows, unpaired = fps.survival(
        evals, os.path.join(HERE, PINNED_CORPUS), fps.vocabulary())
    paired_ids = {c["id"] for c in evals["cases"]
                  if c.get("arms") == ["baseline", "with_skill"]}
    for r in rows:
        assert r["case"] in paired_ids, f"{r['case']} scored without a baseline"
        assert {"baseline", "with_skill"} <= set(r["arms"]), r["case"]
    for r in unpaired:
        assert "baseline" not in r["arms"], f"{r['case']} is unpaired yet has one"
    groups = fps.classify(rows)
    assert sum(len(v) for v in groups.values()) == len(rows), "a row was lost"


@case("TC-EV-86", "a note about the edit is one finding, not three")
def tc86():
    """P4/with_skill/rep-3 rewrote the page correctly and then appended a note
    to the compiler quoting the `[TBD]` it had just removed.

    The grader read that note as part of the copy and failed the run three
    times over: `markers_removed` (the placeholder "survived"), and
    `proportionate_length` (34% growth), while the growth ratio itself was
    computed on copy-plus-note. One violation, three penalties, and none of them
    naming what happened. P4 then read as "the skill is worse than no skill",
    which it was not: with the note scored once, both arms sit at 14/15.
    """
    roster = lexicon.build()
    key = {"must_keep": ["Meridian"], "must_drop": ["TBD"],
           "min_similarity": None, "max_growth": None}
    fixture = ("Meridian is the programme. The September figure is [TBD] until "
               "the audit logs are reconciled. " * 3)
    copy = "Meridian is the programme. September lands once the logs reconcile. " * 3
    note = ("One flag: the September figure is only marked `[TBD]` in your "
            "draft, so I could not put a real number on the page.")

    clean = grade_run.score_run(fixture, copy, key, roster)
    assert clean["commentary"] == "", clean["commentary"]
    assert all(c["passed"] for c in clean["checks"] if c["name"] == "no_commentary")

    withnote = grade_run.score_run(fixture, f"{copy}\n\n---\n\n{note}", key, roster)
    failed = [c["name"] for c in withnote["checks"] if not c["passed"]]
    assert failed == ["no_commentary"], (
        f"a trailing note should fail exactly one check, it failed {failed}")
    assert withnote["commentary_words"] > 0
    # and the note must not enter the removal check or the length ratio
    assert withnote["declared_surfaces_surviving"] == [], \
        "the placeholder was counted as surviving because a NOTE mentions it"
    assert withnote["growth"] == clean["growth"], \
        "the note was counted into the length of the rewrite"


@case("TC-EV-87", "the commentary guard does not fire on ordinary prose")
def tc87():
    """It needs BOTH first person AND talk about the edit. Prose legitimately
    says "I" -- P1's memo does -- and prose legitimately says "draft". Only the
    pair marks a note about the work, and a guard that fires on a first-person
    fixture would make every personal-register case unmeasurable."""
    roster = lexicon.build()
    key = {"must_keep": ["x"], "must_drop": [], "min_similarity": None,
           "max_growth": None}
    for text in (
        "I read the draft on Tuesday and it was fine. x\n\nI still think so.",
        "We shipped it. x\n\nThe next version lands in March.",
        "x\n\nThe original plan was different, and the team changed it.",
    ):
        graded = grade_run.score_run("x " * 40, text, key, roster)
        assert graded["commentary"] == "", \
            f"fired on ordinary prose: {graded['commentary'][:60]!r}"
    # every committed run except the one is clean
    fired = 0
    for c in json.loads(_read(os.path.join(HERE, PINNED_REPORT)))["cases"]:
        for runs in c["arms"].values():
            fired += sum(1 for r in runs if r.get("commentary"))
    assert fired == 0, f"{fired} runs in the pinned corpus carry a note"


def _run_all():
    for name, fn in sorted(globals().items()):
        if name.startswith("tc") and callable(fn) and hasattr(fn, "cid"):
            fn()


def main():
    _run_all()
    failed = [(c, d, e) for c, d, e in _RESULTS if e]
    for cid, desc, err in sorted(_RESULTS):
        mark = "FAIL" if err else "ok  "
        print(f"{mark} {cid}  {desc}")
        if err:
            print(f"       {err}")
    total = len(_RESULTS)
    print(f"\n{total - len(failed)}/{total} cases passed")
    if total != EXPECTED_CASES:
        print(f"case count is {total}, EXPECTED_CASES is {EXPECTED_CASES}",
              file=sys.stderr)
        return 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
