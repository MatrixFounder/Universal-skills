"""OP3 ``html get URL OUTPUT_PATH`` — the raw-bytes verb (obsidian-llm-wiki TASK 072 / Q-072-1).

WHY THIS VERB EXISTS. ``_fetch_lite_html`` (the TEXT path) deliberately refuses a ``%PDF-``
payload, because turndown blows its call stack on binary input. That refusal is correct for
Markdown conversion and fatal for a caller that *wants* the bytes: a consumer needing a
guarded PDF download had no verb to call, so it fell back to a bare ``urllib.request.urlopen``
with no SSRF guard at all.

``get`` closes that hole by exposing the primitive the text path already builds on —
:func:`acquire._http_get_bytes` — WITHOUT the content-type interpretation layered above it.
It therefore bypasses **no guard**: the ladder (scheme allow-list · per-hop
``_assert_public_http`` · DNS resolve-then-PIN · redirect cap · streaming byte cap · bounded
timeout) is the function being called, not a check being skipped.

THE LOAD-BEARING PROPERTY these tests pin: `get` must deliver bytes the text path refuses,
AND must refuse every target the ladder refuses. A suite that only fed it hostile URLs could
pass by refusing everything, so every refusal test is paired with a POSITIVE CONTROL.

Run from ``skills/html/scripts``:  python3 -m pytest html2md/tests/test_get.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

SCRIPTS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if SCRIPTS not in sys.path:
    sys.path.insert(0, SCRIPTS)

from html2md import acquire, cli  # noqa: E402
from html2md.exceptions import FetchFailed  # noqa: E402

TARGET = "https://example.com/paper.pdf"
PDF_BYTES = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n\x00\x01\x02binary\xff\xfe"


class _GetBase(unittest.TestCase):
    """Saves/restores the single network seam, exactly as test_ladder.py does."""

    def setUp(self):
        self._saved = {
            "_http_get_bytes": acquire._http_get_bytes,
            "_host_is_public": acquire._host_is_public,
        }
        self.requested: list[str] = []

    def tearDown(self):
        for k, v in self._saved.items():
            setattr(acquire, k, v)

    def _json_run(self, argv):
        """Run the CLI and return (exit_code, parsed stderr envelope). Asserting on
        `details.kind` is what makes a refusal test discriminating instead of vacuous."""
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            code = cli.main(argv)
        line = buf.getvalue().strip().splitlines()[-1]
        return code, json.loads(line)

    def _seam(self, payload=PDF_BYTES, *, raises=None):
        """Replace the network seam with an offline double that records the URL."""
        def _fake(url, *, max_bytes=None, **kw):
            self.requested.append(url)
            if raises is not None:
                raise raises
            if max_bytes is not None and len(payload) > max_bytes:
                raise FetchFailed(
                    f"response exceeds --max-bytes ({max_bytes})",
                    details={"url": "redacted", "max_bytes": max_bytes},
                )
            return payload
        acquire._http_get_bytes = _fake


class TestGetDeliversBytes(_GetBase):
    def test_writes_bytes_verbatim_including_a_pdf_the_text_path_refuses(self):
        """★ THE REASON THE VERB EXISTS. The same payload that `_fetch_lite_html` rejects
        with `kind: pdf` must land on disk byte-identically — no decode, no sanitize, no
        content sniffing."""
        self._seam()
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "paper.pdf"
            rc = cli.main(["get", TARGET, str(out)])
            self.assertEqual(rc, 0)
            self.assertTrue(out.exists())
            self.assertEqual(out.read_bytes(), PDF_BYTES)

    def test_the_text_path_still_refuses_the_same_payload(self):
        """The CONTROL for the test above: `get` is a different operation, not a weakening
        of `_fetch_lite_html`. If this ever goes green-by-accident, the refusal was removed
        from the text path and turndown is exposed to binary again."""
        self._seam()
        with self.assertRaises(FetchFailed) as ctx:
            acquire._fetch_lite_html(TARGET, None)
        self.assertEqual(ctx.exception.details.get("kind"), "pdf")

    def test_goes_through_the_ladder_seam(self):
        """`get` must call `_http_get_bytes`, not open its own socket. Paired with the
        source-level guard below, this is what keeps the guard IMPORTED, not re-ported."""
        self._seam()
        with tempfile.TemporaryDirectory() as d:
            cli.main(["get", TARGET, str(Path(d) / "o.bin")])
        self.assertEqual(self.requested, [TARGET])

    def test_creates_missing_parent_directories(self):
        self._seam(payload=b"xyz")
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "nested" / "deep" / "o.bin"
            self.assertEqual(cli.main(["get", TARGET, str(out)]), 0)
            self.assertEqual(out.read_bytes(), b"xyz")


class TestGetRefusals(_GetBase):
    """Every refusal is paired with the positive control in TestGetDeliversBytes —
    a guard suite fed only hostile input cannot prove it fails open."""

    def test_non_http_scheme_is_a_CALLER_error_not_a_network_refusal(self):
        """★ A caller mistake must be distinguishable from an SSRF block in the consumer's
        logs. Delegating scheme checking to the ladder reported `html get /tmp/x.pdf` as
        exit 10 'refused non-http(s) target' — i.e. a typo read as a security event (and
        `_redact` mangled the path into `:///tmp/...`). Scheme is now validated up front."""
        for bad in ("file:///etc/passwd", "/tmp/local.pdf", "ftp://example.com/x"):
            with self.subTest(url=bad), tempfile.TemporaryDirectory() as d:
                out = Path(d) / "o.bin"
                self.assertEqual(cli.main(["get", bad, str(out)]), 2)
                self.assertFalse(out.exists())

    def test_a_private_http_target_is_still_a_NETWORK_refusal(self):
        """The control for the test above: exit 10 must remain reserved for a genuine
        security outcome, so the two classes stay distinguishable.

        ★ Asserts `details.kind == "refused"`, NOT merely `rc == 10`. Measured: with
        `_is_ssrf_blocked` disabled these tests still PASSED — the mutant egressed into
        RFC-1918 space and got a real `HTTP 404`, and `_get_main` maps every FetchFailed to
        10, so the assertion could not tell a security refusal from a plain ConnectError.
        The change's most security-load-bearing property had a vacuous regression test.
        `kind` discriminates: guard ON → "refused", guard OFF → "unreachable"."""
        for url in ("http://127.0.0.1/x", "http://169.254.169.254/latest"):
            with self.subTest(url=url), tempfile.TemporaryDirectory() as d:
                out = Path(d) / "o.bin"
                code, payload = self._json_run(
                    ["get", url, str(out), "--retries", "0", "--json-errors"])
                self.assertEqual(code, 10)
                self.assertEqual(payload["details"]["kind"], "refused",
                                 "a plain unreachable host must NOT satisfy this test")
                self.assertFalse(out.exists())

    def test_refuses_control_characters_in_the_url(self):
        """`_assert_safe_target` (the CRLF / request-splitting guard) lives in `_acquire_url`
        — a CALLER of the ladder, not the ladder itself — so `get` calls it explicitly. Until
        it did, the claim 'bypasses no guard' was not literally true. httpx also rejects
        these today, but that is a property of the dependency, not of this skill."""
        self._seam()  # seam installed so a pass-through would reach it and succeed
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "o.bin"
            rc = cli.main(["get", "https://example.com/x\r\nX-Injected: 1", str(out)])
            self.assertEqual(rc, 10)
            self.assertFalse(out.exists())
            self.assertEqual(self.requested, [], "the guard must fire BEFORE the ladder")

    def test_refuses_private_target_through_the_real_guard(self):
        """Same discriminator as above. `--retries 0` because the pre-fix version took 66 s
        on this machine actually egressing to 10.0.0.1 — and still reported success."""
        for url in ("http://127.0.0.1/x", "http://10.0.0.1/x", "http://169.254.169.254/latest"):
            with self.subTest(url=url), tempfile.TemporaryDirectory() as d:
                out = Path(d) / "o.bin"
                code, payload = self._json_run(
                    ["get", url, str(out), "--retries", "0", "--json-errors"])
                self.assertEqual(code, 10)
                self.assertEqual(payload["details"]["kind"], "refused")
                self.assertFalse(out.exists(), "a refused fetch must leave NO file")

    def test_the_refusal_assertion_can_actually_fail(self):
        """★ NON-VACUITY for the two tests above — the control whose absence made them
        meaningless. With the SSRF blocklist disabled the envelope must change `kind`, so the
        assertions are measuring the guard rather than mere unreachability."""
        saved = acquire._is_ssrf_blocked
        acquire._is_ssrf_blocked = lambda ip: False
        try:
            with tempfile.TemporaryDirectory() as d:
                code, payload = self._json_run(
                    ["get", "http://127.0.0.1/x", str(Path(d) / "o.bin"),
                     "--retries", "0", "--timeout", "2", "--json-errors"])
        finally:
            acquire._is_ssrf_blocked = saved
        self.assertEqual(code, 10)
        self.assertNotEqual(payload["details"].get("kind"), "refused",
                            "with the blocklist off this must NOT report a refusal")

    def test_over_cap_writes_nothing(self):
        """A partial file is worse than no file — the caller cannot tell it is truncated."""
        self._seam()
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "o.bin"
            rc = cli.main(["get", TARGET, str(out), "--max-bytes", "4"])
            self.assertEqual(rc, 10)
            self.assertFalse(out.exists())

    def test_fetch_failure_writes_nothing(self):
        self._seam(raises=FetchFailed("boom", details={"url": "redacted"}))
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "o.bin"
            self.assertEqual(cli.main(["get", TARGET, str(out)]), 10)
            self.assertFalse(out.exists())

    def test_json_errors_envelope(self):
        self._seam(raises=FetchFailed("boom", details={"url": "redacted", "kind": "refused"}))
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "o.bin"
            import contextlib
            import io
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                rc = cli.main(["get", TARGET, str(out), "--json-errors"])
            self.assertEqual(rc, 10)
            payload = json.loads(buf.getvalue().strip().splitlines()[-1])
            self.assertEqual(payload["type"], "FetchFailed")
            self.assertEqual(payload["code"], 10)


class TestGetUsage(_GetBase):
    def test_missing_output_is_a_usage_error(self):
        self.assertEqual(cli.main(["get", TARGET]), 2)

    def test_refuses_a_bounded_default_cap_of_zero(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(
                cli.main(["get", TARGET, str(Path(d) / "o.bin"), "--max-bytes", "0"]), 2)

    def test_has_a_bounded_default_cap(self):
        """An unbounded default is fine for HTML (the text path caps elsewhere) and a DoS
        foot-gun for an arbitrary binary download. Pin that the default is finite."""
        self.assertIsNotNone(cli._GET_DEFAULT_MAX_BYTES)
        self.assertGreater(cli._GET_DEFAULT_MAX_BYTES, 0)


class TestGetWriteSafety(_GetBase):
    """The write side. `get` is the only verb that puts UNSANITIZED, fully remote-controlled
    bytes at a caller-named path, so its write hazards are its own, not the skill's."""

    def test_refuses_to_write_through_a_symlink(self):
        """★ Proven exploitable before the fix: `write_bytes` opens 'wb', which FOLLOWS a
        symlink — so `get URL out.bin` where out.bin -> SENSITIVE.txt overwrote the target
        and left the symlink intact, i.e. undetectable. This is the one hazard the caller
        cannot audit from the path string it passed."""
        self._seam(payload=b"attacker bytes")
        with tempfile.TemporaryDirectory() as d:
            secret = Path(d) / "SENSITIVE.txt"
            secret.write_text("original secret")
            link = Path(d) / "out.bin"
            link.symlink_to(secret)
            rc = cli.main(["get", TARGET, str(link)])
            self.assertEqual(rc, 2)
            self.assertEqual(secret.read_text(), "original secret",
                             "the symlink target must be untouched")

    def test_refuses_a_directory_as_output(self):
        self._seam()
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(cli.main(["get", TARGET, d]), 2)

    def test_a_refusal_leaves_a_PRE_EXISTING_output_untouched(self):
        """The docs used to claim 'a refused fetch leaves NO file' unconditionally. That is
        false when the caller pre-created OUTPUT_PATH — and the intended consumer does
        exactly that with `mkstemp`. The true property is: `get` never writes, and never
        unlinks a file it did not create."""
        self._seam(raises=FetchFailed("boom", details={"url": "redacted"}))
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "pre.pdf"
            out.write_bytes(b"caller's placeholder")
            self.assertEqual(cli.main(["get", TARGET, str(out)]), 10)
            self.assertEqual(out.read_bytes(), b"caller's placeholder")

    def test_write_is_atomic_and_leaves_no_part_file(self):
        self._seam(payload=b"final bytes")
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "o.bin"
            self.assertEqual(cli.main(["get", TARGET, str(out)]), 0)
            self.assertEqual(out.read_bytes(), b"final bytes")
            self.assertEqual(list(Path(d).glob("*.part")), [])

    def test_stdout_mode_writes_no_file(self):
        """`--stdout` exists so the HTML consumer (`_download_raw_html`, which returns a str
        and touches no disk today) does not have to grow a temp-file lifecycle."""
        self._seam(payload=b"\x89PNG\r\n\x1a\n")
        with tempfile.TemporaryDirectory() as d:
            rc = cli.main(["get", TARGET, "--stdout"])
            self.assertEqual(rc, 0)
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_output_and_stdout_are_mutually_exclusive(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(cli.main(["get", TARGET, str(Path(d) / "o"), "--stdout"]), 2)
        self.assertEqual(cli.main(["get", TARGET]), 2)


class TestGetWriteHazards(_GetBase):
    """Three failure modes found by probing the FINAL code, not by unit tests. Each surfaced
    as a bare `Internal error: <ExceptionName>` — the shape that tells a caller nothing."""

    def test_a_part_collision_does_not_crash(self):
        """A fixed `<name>.part` collided: an existing directory of that name produced
        `Internal error: PermissionError` and left the directory behind. The temp is now
        `mkstemp`-unique, which also makes two concurrent `get`s to one OUTPUT_PATH safe."""
        self._seam(payload=b"final")
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "x.bin"
            (Path(d) / "x.bin.part").mkdir()          # the old fixed name, now occupied
            self.assertEqual(cli.main(["get", TARGET, str(out)]), 0)
            self.assertEqual(out.read_bytes(), b"final")

    def test_temp_artifacts_are_cleaned_up(self):
        self._seam(payload=b"final")
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "x.bin"
            cli.main(["get", TARGET, str(out)])
            self.assertEqual([p.name for p in Path(d).iterdir()], ["x.bin"])

    def test_artifact_is_not_world_readable(self):
        """`mkstemp` creates 0600 and `os.replace` carries the mode over, so a
        capability-URL artifact (a signed link, a tokenised export) does not land 0644."""
        self._seam(payload=b"secret-ish")
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "x.bin"
            cli.main(["get", TARGET, str(out)])
            self.assertEqual(out.stat().st_mode & 0o077, 0,
                             "group/other bits must be clear")

    def test_browser_ua_conflicting_with_a_ua_header_is_refused(self):
        """`_http_get_bytes` does `headers.update(extra_headers)` AFTER seeding the UA, so the
        header silently WON and `--browser-ua` was a no-op. Verified before the fix: the ua
        kwarg was the browser UA while extra_headers carried `{'User-Agent': 'MINE'}`."""
        self._seam()
        with tempfile.TemporaryDirectory() as d:
            o = str(Path(d) / "o.bin")
            for hdr in ("User-Agent: MINE", "user-agent: mine", "  User-Agent :  X"):
                with self.subTest(header=hdr):
                    self.assertEqual(
                        cli.main(["get", TARGET, o, "--browser-ua", "--header", hdr]), 2)

    def test_each_flag_alone_is_still_accepted(self):
        """The control: the refusal above must be about the CONFLICT, not about either flag."""
        self._seam()
        with tempfile.TemporaryDirectory() as d:
            o = str(Path(d) / "o.bin")
            self.assertEqual(cli.main(["get", TARGET, o, "--browser-ua"]), 0)
            self.assertEqual(cli.main(["get", TARGET, o, "--header", "User-Agent: MINE"]), 0)


class TestGetKnobs(_GetBase):
    def test_rejects_out_of_range_numeric_flags(self):
        """`type=float` accepts 0, -5, 1e9 and nan without complaint, and httpx applies the
        timeout PER OPERATION rather than as a total budget — so an unvalidated value is a
        slow-drip window, not merely a bad number."""
        with tempfile.TemporaryDirectory() as d:
            o = str(Path(d) / "o.bin")
            for flag, value in (("--timeout", "0"), ("--timeout", "-5"),
                                ("--timeout", "nan"), ("--timeout", "1e9"),
                                ("--retries", "-1"), ("--retries", "999999999"),
                                ("--max-bytes", "0"), ("--max-bytes", "-1")):
                with self.subTest(flag=flag, value=value):
                    self.assertEqual(cli.main(["get", TARGET, o, flag, value]), 2)

    def test_headers_are_forwarded(self):
        seen = {}

        def _fake(url, *, max_bytes=None, extra_headers=None, **kw):
            seen["headers"] = extra_headers
            seen["ua"] = kw.get("ua")
            return b"ok"
        acquire._http_get_bytes = _fake
        with tempfile.TemporaryDirectory() as d:
            rc = cli.main(["get", TARGET, str(Path(d) / "o.bin"),
                           "--header", "Accept: application/pdf,*/*",
                           "--header", "X-Trace: 1"])
        self.assertEqual(rc, 0)
        self.assertEqual(seen["headers"],
                         {"Accept": "application/pdf,*/*", "X-Trace": "1"})

    def test_browser_ua_is_forwarded(self):
        seen = {}

        def _fake(url, *, max_bytes=None, **kw):
            seen["ua"] = kw.get("ua")
            return b"ok"
        acquire._http_get_bytes = _fake
        with tempfile.TemporaryDirectory() as d:
            cli.main(["get", TARGET, str(Path(d) / "o.bin"), "--browser-ua"])
        self.assertEqual(seen["ua"], acquire._BROWSER_UA)

    def test_malformed_header_is_a_usage_error(self):
        self._seam()
        with tempfile.TemporaryDirectory() as d:
            o = str(Path(d) / "o.bin")
            for bad in ("no-colon", ": empty-key", "X-Bad: a\rb", "X-Bad\n: c"):
                with self.subTest(header=bad):
                    self.assertEqual(cli.main(["get", TARGET, o, "--header", bad]), 2)

    def test_argparse_usage_errors_also_emit_json(self):
        """★ The consumer parses stderr AS JSON. Without `_errors.add_json_errors_argument`
        a missing positional printed a plain-text usage banner and choked it — and `get` is
        the ONE verb whose documented consumer is another program.

        NOTE the seam being exercised: the helper cannot see parsed args (argparse calls
        `error()` mid-parse), so it scans `sys.argv` — which is correct for the SUBPROCESS
        invocation the consumer uses, and is why this test sets `sys.argv` rather than
        relying on the argv list passed to `main()`."""
        import contextlib
        import io
        buf = io.StringIO()
        saved = sys.argv
        sys.argv = ["html", "get", TARGET, "--max-bytes", "not-a-number", "--json-errors"]
        try:
            with contextlib.redirect_stderr(buf):
                rc = cli.main(["get", TARGET, "--max-bytes", "not-a-number",
                               "--json-errors"])
        finally:
            sys.argv = saved
        self.assertEqual(rc, 2)
        payload = json.loads(buf.getvalue().strip().splitlines()[-1])
        self.assertEqual(payload["code"], 2)
        self.assertEqual(payload["type"], "UsageError")


class TestGetDeadline(_GetBase):
    """★ `--timeout` is PER OPERATION and bounds NOTHING in total. Measured before the fix:
    a 5-hop redirect chain stalling BELOW the timeout ran 2.4x the per-op budget (the factor
    is `max_redirects + 1`, multiplied again by every retry pass — 60 x 6 x 4 = 1440 s at the
    shipped defaults, against a documented ~243 s), and a body dripping one byte per 1.6 s
    returned OK after 12.85 s against a 2 s timeout, unbounded in principle because
    `--max-bytes` caps SIZE and never TIME. `--deadline` is the bound that makes the
    documented number true."""

    def test_deadline_fires_on_a_slow_drip_body(self):
        def _drip(url, *, max_bytes=None, deadline_s=None, **kw):
            end = time.monotonic() + (deadline_s or 0)
            while time.monotonic() <= end:      # a body that never ends, under the byte cap
                time.sleep(0.01)
            raise FetchFailed(f"exceeded the total deadline ({deadline_s}s)",
                              details={"url": "redacted", "kind": "deadline",
                                       "deadline_s": deadline_s})
        acquire._http_get_bytes = _drip
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "o.bin"
            t0 = time.monotonic()
            code, payload = self._json_run(
                ["get", TARGET, str(out), "--deadline", "0.3", "--json-errors"])
        self.assertEqual(code, 10)
        self.assertEqual(payload["details"]["kind"], "deadline")
        self.assertLess(time.monotonic() - t0, 5, "the deadline must actually bound the wall clock")
        self.assertFalse(out.exists())

    def test_deadline_is_forwarded_to_the_ladder(self):
        seen = {}

        def _fake(url, *, max_bytes=None, deadline_s=None, **kw):
            seen["deadline_s"] = deadline_s
            return b"ok"
        acquire._http_get_bytes = _fake
        with tempfile.TemporaryDirectory() as d:
            cli.main(["get", TARGET, str(Path(d) / "o.bin"), "--deadline", "12.5"])
        self.assertEqual(seen["deadline_s"], 12.5)

    def test_default_deadline_is_finite_and_forwarded(self):
        seen = {}

        def _fake(url, *, max_bytes=None, deadline_s=None, **kw):
            seen["deadline_s"] = deadline_s
            return b"ok"
        acquire._http_get_bytes = _fake
        with tempfile.TemporaryDirectory() as d:
            cli.main(["get", TARGET, str(Path(d) / "o.bin")])
        self.assertEqual(seen["deadline_s"], cli._GET_DEFAULT_DEADLINE_S)
        self.assertIsNotNone(cli._GET_DEFAULT_DEADLINE_S)

    def test_out_of_range_deadline_is_a_usage_error(self):
        self._seam()
        with tempfile.TemporaryDirectory() as d:
            o = str(Path(d) / "o.bin")
            for value in ("0", "-1", "nan", "3601"):
                with self.subTest(value=value):
                    self.assertEqual(cli.main(["get", TARGET, o, "--deadline", value]), 2)


class TestLadderDeadline(unittest.TestCase):
    """The deadline is enforced INSIDE the shared ladder (each hop + each chunk), so the whole
    skill gains the bound, not just `get`."""

    def test_ladder_signature_accepts_a_deadline(self):
        import inspect
        sig = inspect.signature(acquire._http_get_bytes)
        self.assertIn("deadline_s", sig.parameters)
        self.assertIsNone(sig.parameters["deadline_s"].default,
                          "None must keep the historical unbounded behaviour for old callers")

    def test_it_is_checked_in_both_loops(self):
        """A deadline checked only between retries would not bound a redirect chain OR a
        drip. Pin both call sites so a refactor cannot quietly drop one."""
        src = Path(SCRIPTS, "html2md", "acquire.py").read_text(encoding="utf-8")
        self.assertIn('_check_deadline("redirect")', src)
        self.assertIn('_check_deadline("body")', src)


class TestGetIsDiscoverable(unittest.TestCase):
    """★ A consumer that DEPENDS on this verb must fail CLOSED on an install that lacks it.
    Both properties below were bugs found during the live smoke test, not by unit tests."""

    def test_verb_help_exits_zero(self):
        """`--help` is a SUCCESS. The first implementation wrote `exc.code or _EXIT_USAGE`,
        and 0 is falsy — so `html get --help` returned 2, i.e. a capability probe would read
        "verb missing" on an install that HAS it."""
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = cli.main(["get", "--help"])
        self.assertEqual(rc, 0)
        self.assertIn("OUTPUT_PATH", buf.getvalue())

    def test_top_level_help_carries_an_unambiguous_probe_string(self):
        """`html <verb> --help` CANNOT be used as a probe: on a copy without the verb,
        argparse treats it as INPUT, sees --help, prints the top-level help and exits 0 — a
        false positive. So the roster must be greppable from the top-level help instead."""
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit):
            cli.build_parser().parse_args(["--help"])
        text = buf.getvalue()
        self.assertIn("html get URL OUTPUT_PATH", text)
        for verb in ("html fetch INPUT", "html md INPUT", "html search QUERY", "html login URL"):
            self.assertIn(verb, text, "the roster must list every verb, not just the new one")

    def test_a_naive_probe_would_false_positive(self):
        """The reason the probe string is `html get URL` and not `get`: the flag help is full
        of incidental matches (`--target-selector`, `targets`). Pinned so nobody 'simplifies'
        the documented probe into a broken one."""
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), self.assertRaises(SystemExit):
            cli.build_parser().parse_args(["--help"])
        naive = [ln for ln in buf.getvalue().splitlines() if "get" in ln]
        self.assertGreater(len(naive), 1,
                           "if this ever drops to 1, a bare `grep -q get` became safe and "
                           "this test may be retired")


class TestGetImportsTheGuard(unittest.TestCase):
    """A source-level guard: the verb must never grow its own HTTP client. This is the
    mechanical form of 'guards are IMPORTED, never re-ported'.

    ★ Deliberately AST-based, not a substring grep. The first version of this test was a
    grep and it failed on `_get_main`'s own docstring, which NAMES `urlopen` in order to
    explain why the verb exists — a guard that cannot tell code from prose about code is a
    guard that gets deleted the first time it cries wolf.
    """

    _BANNED_MODULES = ("urllib", "urllib.request", "http.client", "socket", "httpx",
                       "requests", "aiohttp")
    _BANNED_CALLS = ("urlopen", "urlretrieve", "create_connection")

    def test_cli_imports_no_http_client(self):
        import ast
        tree = ast.parse(Path(SCRIPTS, "html2md", "cli.py").read_text(encoding="utf-8"))
        imported: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported += [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        offenders = [m for m in imported
                     if m in self._BANNED_MODULES
                     or any(m.startswith(b + ".") for b in self._BANNED_MODULES)]
        # `urllib.parse` is pure string work and is legitimately used for URL resolution.
        offenders = [m for m in offenders if not m.startswith("urllib.parse")]
        self.assertEqual(offenders, [],
                         "cli.py must reach the network only via acquire._http_get_bytes")

    def test_cli_calls_no_http_primitive(self):
        import ast
        tree = ast.parse(Path(SCRIPTS, "html2md", "cli.py").read_text(encoding="utf-8"))
        called = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", None)
            if name:
                called.add(name)
        self.assertEqual(sorted(called & set(self._BANNED_CALLS)), [])

    def test_the_guard_can_actually_fire(self):
        """Non-vacuity: prove the AST checks detect a real violation, or they are two
        assertions that pass because nothing can ever match."""
        import ast
        bad = ast.parse("import urllib.request\nurllib.request.urlopen('x')\n")
        imported = [a.name for n in ast.walk(bad) if isinstance(n, ast.Import)
                    for a in n.names]
        self.assertTrue(any(m.startswith("urllib.request") for m in imported))
        calls = {n.func.attr for n in ast.walk(bad)
                 if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)}
        self.assertIn("urlopen", calls)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
