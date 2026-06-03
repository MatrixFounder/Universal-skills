"""Tests for `pdf_ocr.py` — the scanned-PDF → searchable-PDF OCR wrapper (TASK 018).

Stub-First (`tdd-stub-first`): task 018-01 lands the `--help` smoke E2E + the
stub-phase unit cluster (parser/mutex/path-guards are REAL; engine/lang/runner
are stubs). Tasks 018-02 / 018-03 UPDATE the assertions as logic lands.

Engine note: `pdf_ocr.py` imports `ocrmypdf` lazily, so EVERY test in this file
runs WITHOUT the OCR engine installed (the real-OCR composition E2E lives in
018-03 and soft-skips when the engine is absent).

Run:
    cd skills/pdf/scripts
    ./.venv/bin/python -m unittest tests.test_pdf_ocr -v
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS_DIR))

import pdf_ocr  # noqa: E402

from tests import _pdf_ocr_fixtures as fixtures  # noqa: E402


def _run_main_json(argv: list[str]) -> tuple[int, dict | None]:
    """Run `pdf_ocr.py argv --json-errors` as a subprocess; return
    `(exit_code, parsed_envelope_or_None)`.

    A subprocess (not an in-process `main()` call) is used so the real process
    exit code is observed AND the `_errors.report_error` envelope is captured:
    `report_error`'s `stream=sys.stderr` default binds at import time, so
    `contextlib.redirect_stderr` would NOT intercept it."""
    r = subprocess.run(
        [sys.executable, "pdf_ocr.py", *argv, "--json-errors"],
        cwd=str(SCRIPTS_DIR), capture_output=True, text=True,
    )
    lines = r.stderr.strip().splitlines()
    envelope = json.loads(lines[-1]) if lines else None
    return r.returncode, envelope


class TestHelpSmoke(unittest.TestCase):
    """TC-E2E-01 — the `--help` surface is the Phase-1 smoke gate."""

    def test_help_lists_surface(self) -> None:
        r = subprocess.run(
            [sys.executable, "pdf_ocr.py", "--help"],
            cwd=str(SCRIPTS_DIR), capture_output=True, text=True,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        out = r.stdout
        for needle in (
            "INPUT", "OUTPUT", "--lang", "--skip-text", "--redo-ocr",
            "--force-ocr", "--sidecar", "--json-errors", "searchable", "eng+rus",
        ):
            self.assertIn(needle, out, f"--help missing {needle!r}")


class TestStubUnits(unittest.TestCase):
    """TC-UNIT-01..08 — stub-phase contract."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.mkdtemp(prefix="pdf_ocr_test_")
        cls._fx = _SHARED_FX

    @classmethod
    def tearDownClass(cls) -> None:
        for p in Path(cls._tmp).glob("*"):
            with contextlib.suppress(OSError):
                p.unlink()
        with contextlib.suppress(OSError):
            os.rmdir(cls._tmp)

    def test_module_imports_without_ocrmypdf(self) -> None:
        # TC-UNIT-01: importing pdf_ocr must NOT import ocrmypdf at module top.
        # Force ocrmypdf unimportable in a subprocess and assert the import works.
        code = (
            "import sys; sys.modules['ocrmypdf'] = None; "
            "import pdf_ocr; print('OK')"
        )
        r = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(SCRIPTS_DIR), capture_output=True, text=True,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("OK", r.stdout)

    def test_constants_locked(self) -> None:
        # TC-UNIT-02
        self.assertEqual(pdf_ocr._EXIT_OK, 0)
        self.assertEqual(pdf_ocr._EXIT_FAIL, 1)
        self.assertEqual(pdf_ocr._EXIT_USAGE, 2)
        self.assertEqual(pdf_ocr._EXIT_SELF_OVERWRITE, 6)
        self.assertEqual(pdf_ocr._DEFAULT_LANG, "eng+rus")

    def test_mode_mutex(self) -> None:
        # TC-UNIT-03
        parser = pdf_ocr._build_parser()
        ns = parser.parse_args(["in.pdf", "out.pdf"])
        self.assertEqual(ns.mode, "skip_text")  # default
        with self.assertRaises(SystemExit):  # mutex violation → argparse exit 2
            parser.parse_args(["in.pdf", "out.pdf", "--redo-ocr", "--force-ocr"])

    def test_same_path_guard(self) -> None:
        # TC-UNIT-04 — needs a real existing input (existence is checked first).
        scan = self._fx["scan"]
        code, env = _run_main_json([str(scan), str(scan)])
        self.assertEqual(code, 6)
        self.assertEqual(env["type"], "SelfOverwriteRefused")
        # symlink alias → still 6
        link = Path(self._tmp) / "alias.pdf"
        with contextlib.suppress(FileExistsError):
            os.symlink(scan, link)
        code2, env2 = _run_main_json([str(scan), str(link)])
        self.assertEqual(code2, 6)
        self.assertEqual(env2["type"], "SelfOverwriteRefused")

    def test_sidecar_collision_guard(self) -> None:
        # TC-UNIT-05
        scan = self._fx["scan"]
        out = Path(self._tmp) / "out.pdf"
        code, env = _run_main_json(
            [str(scan), str(out), "--sidecar", str(out)]
        )
        self.assertEqual(code, 6)
        self.assertEqual(env["type"], "SelfOverwriteRefused")

    def test_input_not_found(self) -> None:
        # TC-UNIT-06
        missing = Path(self._tmp) / "nope.pdf"
        out = Path(self._tmp) / "out.pdf"
        code, env = _run_main_json([str(missing), str(out)])
        self.assertEqual(code, 1)
        self.assertEqual(env["type"], "InputNotFound")

    def test_fixtures_build(self) -> None:
        # TC-UNIT-08 — scan.pdf is image-only; digital.pdf has selectable text.
        import pdfplumber  # type: ignore

        with pdfplumber.open(str(self._fx["scan"])) as pdf:
            page = pdf.pages[0]
            self.assertTrue(page.images, "scan.pdf page should carry an image")
            self.assertEqual(
                (page.extract_text() or "").strip(), "",
                "scan.pdf must have NO extractable text layer",
            )
        with pdfplumber.open(str(self._fx["digital"])) as pdf:
            txt = (pdf.pages[0].extract_text() or "").strip()
            self.assertIn("selectable", txt.lower())


def _engine_present() -> bool:
    try:
        __import__("ocrmypdf")
        return True
    except ImportError:
        return False


def _ocr_stack_present() -> bool:
    """The full real-OCR stack: ocrmypdf importable + tesseract + ghostscript."""
    return bool(
        _engine_present()
        and shutil.which("tesseract")
        and shutil.which("gs")
    )


def _pikepdf_present() -> bool:
    try:
        __import__("pikepdf")
        return True
    except ImportError:
        return False


_PIPELINE_OK: "bool | None" = None


def _ocr_pipeline_works() -> bool:
    """True only if a real scan → OCR actually SUCCEEDS on this host — distinct
    from `_ocr_stack_present()` (binaries installed). Some hosts have the
    binaries but a tesseract that cannot read ocrmypdf's nested temp dir (e.g. a
    sandboxed environment that confines spawned binaries to shallow paths); there
    the real OCR is unverifiable and the tesseract-dependent E2Es soft-skip.
    Cached — the probe runs one real OCR."""
    global _PIPELINE_OK
    if _PIPELINE_OK is None:
        if not _ocr_stack_present():
            _PIPELINE_OK = False
        else:
            try:
                d = tempfile.mkdtemp(prefix="ocr_probe_")
                fixtures.build_scan_pdf(Path(d) / "p.pdf")
                r = subprocess.run(
                    [sys.executable, "pdf_ocr.py",
                     str(Path(d) / "p.pdf"), str(Path(d) / "p.ocr.pdf")],
                    cwd=str(SCRIPTS_DIR), capture_output=True, text=True,
                )
                _PIPELINE_OK = r.returncode == 0
            except Exception:
                _PIPELINE_OK = False
    return _PIPELINE_OK


_PIPELINE_SKIP = (
    "OCR pipeline non-functional on this host: the OCR binaries are installed "
    "but tesseract cannot read ocrmypdf's nested temp dir (e.g. a sandboxed "
    "environment). Run `bash tests/test_e2e.sh` in a normal shell to verify the "
    "composition; see references/ocr.md."
)


class _FakeOcr:
    """A stand-in for the `ocrmypdf` module: `.ocr(**kwargs)` records the kwargs
    and delegates to a `behavior` callable (which writes the output_file and/or
    raises). Patched in via `pdf_ocr._require_engine` so the runner logic is
    exercised WITHOUT the real engine."""

    def __init__(self, behavior) -> None:  # noqa: ANN001
        self.behavior = behavior
        self.captured: dict | None = None

    def ocr(self, input_file=None, output_file=None, **kwargs):  # noqa: ANN001, ANN003, ANN201
        # Mirror the real signature: ocrmypdf.ocr takes the two paths
        # POSITIONALLY. Fold them into `captured` so tests can assert on them.
        self.captured = {
            "input_file": input_file, "output_file": output_file, **kwargs,
        }
        return self.behavior(self.captured)


# Module-level shared READ-ONLY fixtures: scan.pdf + digital.pdf are built ONCE
# (Pillow raster + reportlab is the dominant cost of the engine-absent suite).
# Classes reference these for INPUT reads and write OUTPUTS into their own
# per-class tmp dirs — the fixtures are never mutated, so no per-class rebuild.
_SHARED_DIR: "str | None" = None
_SHARED_FX: dict = {}


def setUpModule() -> None:
    global _SHARED_DIR
    _SHARED_DIR = tempfile.mkdtemp(prefix="pdf_ocr_shared_")
    _SHARED_FX.update(fixtures.build_all(Path(_SHARED_DIR)))


def tearDownModule() -> None:
    if _SHARED_DIR:
        for p in Path(_SHARED_DIR).glob("*"):
            with contextlib.suppress(OSError):
                p.unlink()
        with contextlib.suppress(OSError):
            os.rmdir(_SHARED_DIR)


class TestEngineProbeAndLangValidate(unittest.TestCase):
    """018-02 [LOGIC] — FC-3 engine probe + FC-4 language validator.

    All engine-free: the missing-engine path is forced via a patched import; the
    validator is exercised with an explicit installed-set so no real tesseract is
    needed."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.mkdtemp(prefix="pdf_ocr_t2_")
        cls._fx = _SHARED_FX

    @classmethod
    def tearDownClass(cls) -> None:
        for p in Path(cls._tmp).glob("*"):
            with contextlib.suppress(OSError):
                p.unlink()
        with contextlib.suppress(OSError):
            os.rmdir(cls._tmp)

    def test_require_engine_missing(self) -> None:
        # TC-UNIT-09 — force `import ocrmypdf` to fail; expect OcrEngineUnavailable.
        real_import = __import__

        def fake_import(name, *a, **k):  # noqa: ANN001, ANN202
            if name == "ocrmypdf":
                raise ImportError("simulated absence")
            return real_import(name, *a, **k)

        with mock.patch("builtins.__import__", side_effect=fake_import):
            with self.assertRaises(pdf_ocr._OcrError) as ctx:
                pdf_ocr._require_engine()
        self.assertEqual(ctx.exception.error_type, "OcrEngineUnavailable")
        self.assertIn("--with-ocr", ctx.exception.message)

    def test_validate_languages_default(self) -> None:
        # TC-UNIT-10
        self.assertEqual(
            pdf_ocr._validate_languages("eng+rus", {"eng", "rus", "osd"}),
            ["eng", "rus"],
        )

    def test_validate_languages_missing(self) -> None:
        # TC-UNIT-11
        with self.assertRaises(pdf_ocr._OcrError) as ctx:
            pdf_ocr._validate_languages("eng+deu", {"eng", "rus"})
        self.assertEqual(ctx.exception.error_type, "LanguagePackMissing")
        self.assertIn("deu", ctx.exception.message)
        self.assertEqual(ctx.exception.details["missing"], ["deu"])

    def test_validate_languages_order_preserved(self) -> None:
        # TC-UNIT-12
        self.assertEqual(
            pdf_ocr._validate_languages("rus+eng", {"eng", "rus"}),
            ["rus", "eng"],
        )

    def test_validate_languages_empty(self) -> None:
        # TC-UNIT-13
        with self.assertRaises(pdf_ocr._OcrError) as ctx:
            pdf_ocr._validate_languages("+", {"eng", "rus"})
        self.assertEqual(ctx.exception.error_type, "LanguagePackMissing")

    def test_installed_languages_parsing(self) -> None:
        # TC-UNIT-L4 — direct coverage of the `tesseract --list-langs` parser:
        # banner-on-stdout (older), banner-on-stderr (newer), blank lines.
        import subprocess as _sp

        def fake_run(argv, **kw):  # noqa: ANN001, ANN202
            return _sp.CompletedProcess(argv, 0, stdout=self._STDOUT, stderr=self._STDERR)

        # (a) older form: banner + langs all on stdout.
        self._STDOUT = "List of available languages (3):\neng\nosd\nrus\n"
        self._STDERR = ""
        with mock.patch.object(pdf_ocr.shutil, "which", return_value="/usr/bin/tesseract"), \
             mock.patch.object(pdf_ocr.subprocess, "run", side_effect=fake_run):
            self.assertEqual(pdf_ocr._installed_languages(), {"eng", "osd", "rus"})

        # (b) newer form: banner on stderr, langs on stdout, trailing blank.
        self._STDOUT = "eng\nrus\n\n"
        self._STDERR = 'List of available languages in "/opt/share" (2):'
        with mock.patch.object(pdf_ocr.shutil, "which", return_value="/usr/bin/tesseract"), \
             mock.patch.object(pdf_ocr.subprocess, "run", side_effect=fake_run):
            self.assertEqual(pdf_ocr._installed_languages(), {"eng", "rus"})

    def test_installed_languages_tesseract_missing(self) -> None:
        # TC-UNIT-L4b — tesseract not on PATH → OcrEngineUnavailable.
        with mock.patch.object(pdf_ocr.shutil, "which", return_value=None):
            with self.assertRaises(pdf_ocr._OcrError) as ctx:
                pdf_ocr._installed_languages()
        self.assertEqual(ctx.exception.error_type, "OcrEngineUnavailable")

    def test_main_engine_path(self) -> None:
        # TC-E2E-02 / updated TC-UNIT-07 — engine-aware end-to-end.
        scan = self._fx["scan"]
        out = Path(self._tmp) / "fresh_out.pdf"
        code, env = _run_main_json([str(scan), str(out)])
        if _engine_present():
            # Engine present: must NOT report OcrEngineUnavailable. (May still be
            # LanguagePackMissing if eng/rus absent, or the sentinel/real path.)
            self.assertNotEqual(
                (env or {}).get("type"), "OcrEngineUnavailable",
                "engine present yet reported unavailable",
            )
        else:
            self.assertEqual(code, 1)
            self.assertEqual(env["type"], "OcrEngineUnavailable")
            self.assertIn("--with-ocr", env["error"])


class TestOcrRunner(unittest.TestCase):
    """018-03 [LOGIC] — FC-5 runner + FC-6 exception mapping, all via a fake
    engine (no real ocrmypdf/tesseract needed)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.mkdtemp(prefix="pdf_ocr_t3_")
        cls._fx = _SHARED_FX

    @classmethod
    def tearDownClass(cls) -> None:
        for p in Path(cls._tmp).glob("*"):
            with contextlib.suppress(OSError):
                p.unlink()
        with contextlib.suppress(OSError):
            os.rmdir(cls._tmp)

    def _run(self, out: Path, behavior, **overrides):  # noqa: ANN001, ANN202
        fake = _FakeOcr(behavior)
        kw = dict(
            lang=["eng", "rus"], mode="skip_text", sidecar=None, jobs=None,
            password=None, deskew=False, rotate_pages=False, clean=False,
        )
        kw.update(overrides)
        with mock.patch.object(pdf_ocr, "_require_engine", return_value=fake):
            code = pdf_ocr.run_ocr(self._fx["scan"], out, **kw)
        return code, fake

    def test_success_atomic_and_mode_kwarg(self) -> None:
        # TC-UNIT-16 — success: output written, exactly-one mode kwarg, lang/jobs.
        out = Path(self._tmp) / "ok.pdf"

        def behavior(kwargs):  # noqa: ANN001, ANN202
            Path(kwargs["output_file"]).write_bytes(b"%PDF-1.7 fake\n")

        code, fake = self._run(out, behavior, mode="redo_ocr", jobs=2)
        self.assertEqual(code, 0)
        self.assertTrue(out.exists())
        # The .partial is an mkstemp scratch (unpredictable name, O_EXCL, 0600);
        # it must be moved away on success, leaving none behind.
        self.assertEqual(list(Path(self._tmp).glob("*.partial.pdf")), [])
        self.assertTrue(fake.captured["redo_ocr"])
        self.assertNotIn("skip_text", fake.captured)
        self.assertNotIn("force_ocr", fake.captured)
        self.assertEqual(fake.captured["language"], ["eng", "rus"])
        self.assertEqual(fake.captured["jobs"], 2)
        self.assertTrue(fake.captured["output_file"].endswith(".partial.pdf"))
        self.assertEqual(Path(fake.captured["output_file"]).parent, Path(self._tmp))

    def test_atomic_no_partial_on_failure(self) -> None:
        # TC-UNIT-14 — engine writes the partial then raises → nothing left (I-3).
        out = Path(self._tmp) / "fail.pdf"

        def behavior(kwargs):  # noqa: ANN001, ANN202
            Path(kwargs["output_file"]).write_bytes(b"partial")
            raise RuntimeError("boom")

        with self.assertRaises(pdf_ocr._OcrError) as ctx:
            self._run(out, behavior)
        self.assertEqual(ctx.exception.error_type, "InternalError")
        self.assertFalse(out.exists(), "no OUTPUT on failure")
        self.assertEqual(
            list(Path(self._tmp).glob("*.partial.pdf")), [], "no partial left"
        )

    def test_nonzero_exitcode_is_failure(self) -> None:
        # TC-UNIT-L1 — ocrmypdf RETURNS a non-zero ExitCode (does not raise) for
        # some failures; run_ocr must NOT promote that to success (HIGH-L1).
        out = Path(self._tmp) / "rc.pdf"

        def behavior(kwargs):  # noqa: ANN001, ANN202
            Path(kwargs["output_file"]).write_bytes(b"%PDF bad\n")
            return 4  # ExitCode.invalid_output_pdf

        with self.assertRaises(pdf_ocr._OcrError) as ctx:
            self._run(out, behavior)
        self.assertEqual(ctx.exception.error_type, "OutputWriteFailed")
        self.assertEqual(ctx.exception.details["ocrmypdf_exit"], 4)
        self.assertFalse(out.exists(), "bad output not promoted to success")
        self.assertEqual(list(Path(self._tmp).glob("*.partial.pdf")), [])

    def test_unwritable_output_dir_maps_cleanly(self) -> None:
        # iter-2 HIGH — mkstemp on a nonexistent OUTPUT dir must map to a clean
        # OutputWriteFailed envelope, never escape as a raw OSError/traceback.
        out = Path(self._tmp) / "nope" / "out.pdf"  # parent does not exist
        with self.assertRaises(pdf_ocr._OcrError) as ctx:
            self._run(out, lambda kwargs: None)
        self.assertEqual(ctx.exception.error_type, "OutputWriteFailed")

    def test_exception_mapping(self) -> None:
        # TC-UNIT-15 — every _ENGINE_EXC_MAP entry → the right envelope `type`,
        # plus the OSError and unmapped-exception fallbacks.
        out = Path(self._tmp) / "map.pdf"
        # All 8 mapped class names (assert the map itself stays in sync).
        cases = [
            ("EncryptedPdfError", "EncryptedInput"),
            ("PriorOcrFoundError", "PriorOcrFound"),
            ("InputFileError", "InputUnreadable"),
            ("BadArgsError", "InputUnreadable"),
            ("UnsupportedImageFormatError", "InputUnreadable"),
            ("DpiError", "InputUnreadable"),
            ("MissingDependencyError", "OcrEngineUnavailable"),
            ("OutputFileAccessError", "OutputWriteFailed"),
        ]
        self.assertEqual(
            {n for n, _ in cases}, set(pdf_ocr._ENGINE_EXC_MAP),
            "test cases out of sync with _ENGINE_EXC_MAP",
        )
        for exc_name, expected in cases:
            with self.subTest(exc=exc_name):
                fake_exc = type(exc_name, (Exception,), {})

                def behavior(kwargs, _e=fake_exc):  # noqa: ANN001, ANN202
                    raise _e("simulated")

                with self.assertRaises(pdf_ocr._OcrError) as ctx:
                    self._run(out, behavior)
                self.assertEqual(ctx.exception.error_type, expected)

        # OSError fallback → OutputWriteFailed.
        with self.subTest(exc="OSError"):
            def os_behavior(kwargs):  # noqa: ANN001, ANN202
                raise OSError("disk full")

            with self.assertRaises(pdf_ocr._OcrError) as ctx:
                self._run(out, os_behavior)
            self.assertEqual(ctx.exception.error_type, "OutputWriteFailed")

        # Unmapped exception → InternalError.
        with self.subTest(exc="ValueError"):
            def val_behavior(kwargs):  # noqa: ANN001, ANN202
                raise ValueError("???")

            with self.assertRaises(pdf_ocr._OcrError) as ctx:
                self._run(out, val_behavior)
            self.assertEqual(ctx.exception.error_type, "InternalError")


@unittest.skipUnless(
    _ocr_stack_present(),
    "OCR stack absent — `bash install.sh --with-ocr` + system tesseract "
    "(eng,rus) + ghostscript to run the real composition E2E",
)
class TestComposition(unittest.TestCase):
    """018-03 — TC-E2E-03/04/05. The architecture's acceptance hinge: a real
    scan → OCR → pdf_extract digital re-read. SKIPPED unless the engine + tools
    are installed (PR-1: pdf-4 may be marked DONE only when this actually runs)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.mkdtemp(prefix="pdf_ocr_comp_")
        cls._fx = _SHARED_FX

    @classmethod
    def tearDownClass(cls) -> None:
        for p in Path(cls._tmp).glob("*"):
            with contextlib.suppress(OSError):
                p.unlink()
        with contextlib.suppress(OSError):
            os.rmdir(cls._tmp)

    def _ocr(self, out: Path, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "pdf_ocr.py", str(self._fx["scan"]), str(out), *extra],
            cwd=str(SCRIPTS_DIR), capture_output=True, text=True,
        )

    def test_composition_roundtrip(self) -> None:
        # TC-E2E-03 — the hinge (needs a working tesseract pipeline).
        if not _ocr_pipeline_works():
            self.skipTest(_PIPELINE_SKIP)
        out = Path(self._tmp) / "scan.ocr.pdf"
        r = self._ocr(out)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(out.exists())
        # pdf_extract must now read it as digital with the ASCII needle present.
        ext = subprocess.run(
            [sys.executable, "pdf_extract.py", str(out)],
            cwd=str(SCRIPTS_DIR), capture_output=True, text=True,
        )
        self.assertEqual(ext.returncode, 0, ext.stderr)
        dump = json.loads(ext.stdout)
        self.assertFalse(dump["doc_scanned"], "OCR'd PDF should not be doc_scanned")
        text = " ".join(p["text"] for p in dump["pages"]).lower()
        self.assertIn("2026", text)
        self.assertIn("hello", text)

    def test_sidecar_emitted(self) -> None:
        # TC-E2E-04 (needs a working tesseract pipeline).
        if not _ocr_pipeline_works():
            self.skipTest(_PIPELINE_SKIP)
        out = Path(self._tmp) / "side.ocr.pdf"
        sidecar = Path(self._tmp) / "side.txt"
        r = self._ocr(out, "--sidecar", str(sidecar))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(sidecar.exists())
        self.assertIn("2026", sidecar.read_text(encoding="utf-8", errors="ignore"))

    def test_skip_text_noop_on_digital(self) -> None:
        # TC-E2E-05 — default --skip-text on a born-digital PDF: no crash.
        out = Path(self._tmp) / "digi.ocr.pdf"
        r = subprocess.run(
            [sys.executable, "pdf_ocr.py", str(self._fx["digital"]), str(out)],
            cwd=str(SCRIPTS_DIR), capture_output=True, text=True,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(out.exists())


@unittest.skipUnless(_pikepdf_present(), "pikepdf absent (ships with ocrmypdf)")
class TestPasswordDecrypt(unittest.TestCase):
    """018-04 [LOGIC] — --password decrypt-to-temp. The decrypt-unit tests need
    only pikepdf (present with the engine); the encrypted OCR roundtrip is gated
    on a working tesseract pipeline."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.mkdtemp(prefix="pdf_ocr_pw_")
        cls._enc = Path(cls._tmp) / "enc.pdf"
        fixtures.build_encrypted_scan(cls._enc, password="test-pw")

    @classmethod
    def tearDownClass(cls) -> None:
        for p in Path(cls._tmp).glob("*"):
            with contextlib.suppress(OSError):
                p.unlink()
        with contextlib.suppress(OSError):
            os.rmdir(cls._tmp)

    def test_decrypt_temp_mode_0600(self) -> None:
        # TC-UNIT-17 — decrypted scratch is created 0600 in the OUTPUT dir.
        out_dir = Path(self._tmp)
        tmp = pdf_ocr._decrypt_to_temp(self._enc, "test-pw", out_dir)
        try:
            self.assertTrue(tmp.exists())
            self.assertEqual(tmp.parent, out_dir)
            self.assertEqual(oct(tmp.stat().st_mode & 0o777), "0o600")
            # The decrypted output is a real, now-unencrypted PDF.
            import pikepdf  # noqa: PLC0415
            with pikepdf.open(str(tmp)) as pdf:  # opens with no password
                self.assertGreaterEqual(len(pdf.pages), 1)
        finally:
            with contextlib.suppress(OSError):
                tmp.unlink()

    def test_wrong_password_maps(self) -> None:
        # TC-UNIT-19
        with self.assertRaises(pdf_ocr._OcrError) as ctx:
            pdf_ocr._decrypt_to_temp(self._enc, "WRONG", Path(self._tmp))
        self.assertEqual(ctx.exception.error_type, "EncryptedInput")

    def test_decrypt_temp_shredded_on_success_and_failure(self) -> None:
        # TC-UNIT-18 — run_ocr removes the decrypted scratch on BOTH paths.
        before = set(Path(self._tmp).glob("*.dec.pdf"))
        self.assertEqual(before, set(), "no stale scratch before")

        # Success path (fake engine writes the partial).
        out = Path(self._tmp) / "ok.pdf"

        def ok_behavior(kwargs):  # noqa: ANN001, ANN202
            Path(kwargs["output_file"]).write_bytes(b"%PDF-1.7 fake\n")

        with mock.patch.object(pdf_ocr, "_require_engine", return_value=_FakeOcr(ok_behavior)):
            pdf_ocr.run_ocr(
                self._enc, out, lang=["eng"], mode="skip_text", sidecar=None,
                jobs=None, password="test-pw", deskew=False, rotate_pages=False,
                clean=False,
            )
        self.assertTrue(out.exists())
        self.assertEqual(set(Path(self._tmp).glob("*.dec.pdf")), set(), "scratch shredded on success")

        # Failure path (fake engine raises after the decrypt).
        out2 = Path(self._tmp) / "fail.pdf"

        def boom_behavior(kwargs):  # noqa: ANN001, ANN202
            raise RuntimeError("boom")

        with mock.patch.object(pdf_ocr, "_require_engine", return_value=_FakeOcr(boom_behavior)):
            with self.assertRaises(pdf_ocr._OcrError):
                pdf_ocr.run_ocr(
                    self._enc, out2, lang=["eng"], mode="skip_text", sidecar=None,
                    jobs=None, password="test-pw", deskew=False, rotate_pages=False,
                    clean=False,
                )
        self.assertFalse(out2.exists())
        self.assertEqual(set(Path(self._tmp).glob("*.dec.pdf")), set(), "scratch shredded on failure")

    def test_encrypted_roundtrip(self) -> None:
        # TC-E2E-07 — full decrypt → OCR → unencrypted searchable PDF.
        if not _ocr_pipeline_works():
            self.skipTest(_PIPELINE_SKIP)
        out = Path(self._tmp) / "enc.ocr.pdf"
        r = subprocess.run(
            [sys.executable, "pdf_ocr.py", str(self._enc), str(out), "--password", "test-pw"],
            cwd=str(SCRIPTS_DIR), capture_output=True, text=True,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(out.exists())
        import pikepdf  # noqa: PLC0415
        with pikepdf.open(str(out)) as pdf:  # output is unencrypted
            self.assertGreaterEqual(len(pdf.pages), 1)

    def test_encrypted_wrong_password_e2e(self) -> None:
        # TC-E2E-08 — wrong password fails loud (no tesseract needed).
        out = Path(self._tmp) / "wp.pdf"
        code, env = _run_main_json([str(self._enc), str(out), "--password", "NOPE"])
        self.assertEqual(code, 1)
        self.assertEqual(env["type"], "EncryptedInput")

    def test_encrypted_no_password_e2e(self) -> None:
        # TC-E2E-09 — encrypted input, no --password → loud (no tesseract needed).
        out = Path(self._tmp) / "np.pdf"
        code, env = _run_main_json([str(self._enc), str(out)])
        self.assertEqual(code, 1)
        self.assertEqual(env["type"], "EncryptedInput")


class TestImagePrepKnobs(unittest.TestCase):
    """018-05 [LOGIC] — --deskew / --rotate-pages / --clean pass-throughs with
    osd/unpaper prerequisite probes. The prereq-refusal paths are engine-free
    (fake engine + patched probes); the real --deskew run is pipeline-gated."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.mkdtemp(prefix="pdf_ocr_knobs_")
        cls._fx = _SHARED_FX

    @classmethod
    def tearDownClass(cls) -> None:
        for p in Path(cls._tmp).glob("*"):
            with contextlib.suppress(OSError):
                p.unlink()
        with contextlib.suppress(OSError):
            os.rmdir(cls._tmp)

    def test_rotate_requires_osd(self) -> None:
        # TC-UNIT-20 — osd missing → LanguagePackMissing naming osd.
        out = Path(self._tmp) / "r.pdf"
        with mock.patch.object(pdf_ocr, "_require_engine", return_value=_FakeOcr(lambda k: None)), \
             mock.patch.object(pdf_ocr, "_installed_languages", return_value={"eng", "rus"}):
            with self.assertRaises(pdf_ocr._OcrError) as ctx:
                pdf_ocr.run_ocr(
                    self._fx["scan"], out, lang=["eng"], mode="skip_text",
                    sidecar=None, jobs=None, password=None, deskew=False,
                    rotate_pages=True, clean=False,
                )
        self.assertEqual(ctx.exception.error_type, "LanguagePackMissing")
        self.assertIn("osd", ctx.exception.message)

    def test_clean_requires_unpaper(self) -> None:
        # TC-UNIT-21 — unpaper missing → OcrEngineUnavailable naming unpaper.
        out = Path(self._tmp) / "c.pdf"
        with mock.patch.object(pdf_ocr, "_require_engine", return_value=_FakeOcr(lambda k: None)), \
             mock.patch.object(pdf_ocr.shutil, "which", return_value=None):
            with self.assertRaises(pdf_ocr._OcrError) as ctx:
                pdf_ocr.run_ocr(
                    self._fx["scan"], out, lang=["eng"], mode="skip_text",
                    sidecar=None, jobs=None, password=None, deskew=False,
                    rotate_pages=False, clean=True,
                )
        self.assertEqual(ctx.exception.error_type, "OcrEngineUnavailable")
        self.assertIn("unpaper", ctx.exception.message)

    def test_knob_kwargs_passed(self) -> None:
        # TC-UNIT-22 — when prereqs satisfied, the kwargs reach ocrmypdf.
        out = Path(self._tmp) / "k.pdf"

        def behavior(kwargs):  # noqa: ANN001, ANN202
            Path(kwargs["output_file"]).write_bytes(b"%PDF-1.7 fake\n")

        fake = _FakeOcr(behavior)
        with mock.patch.object(pdf_ocr, "_require_engine", return_value=fake), \
             mock.patch.object(pdf_ocr, "_installed_languages", return_value={"eng", "osd"}), \
             mock.patch.object(pdf_ocr.shutil, "which", return_value="/usr/bin/unpaper"):
            code = pdf_ocr.run_ocr(
                self._fx["scan"], out, lang=["eng"], mode="skip_text",
                sidecar=None, jobs=None, password=None, deskew=True,
                rotate_pages=True, clean=True,
            )
        self.assertEqual(code, 0)
        self.assertTrue(fake.captured["deskew"])
        self.assertTrue(fake.captured["rotate_pages"])
        self.assertTrue(fake.captured["clean"])

    def test_clean_missing_unpaper_e2e(self) -> None:
        # TC-E2E-11 — real CLI: --clean with unpaper absent fails loud (no
        # tesseract needed). When unpaper IS present, skip (covered by units).
        if shutil.which("unpaper") is not None:
            self.skipTest("unpaper present — missing-path covered by unit test")
        if not _ocr_stack_present():
            self.skipTest("OCR engine absent")
        out = Path(self._tmp) / "ce.pdf"
        code, env = _run_main_json([str(self._fx["scan"]), str(out), "--clean"])
        self.assertEqual(code, 1)
        self.assertEqual(env["type"], "OcrEngineUnavailable")
        self.assertIn("unpaper", env["error"])

    def test_deskew_runs(self) -> None:
        # TC-E2E-10 — real --deskew (needs a working tesseract pipeline).
        if not _ocr_pipeline_works():
            self.skipTest(_PIPELINE_SKIP)
        out = Path(self._tmp) / "d.pdf"
        r = subprocess.run(
            [sys.executable, "pdf_ocr.py", str(self._fx["scan"]), str(out), "--deskew"],
            cwd=str(SCRIPTS_DIR), capture_output=True, text=True,
        )
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(out.exists())


if __name__ == "__main__":
    unittest.main()
