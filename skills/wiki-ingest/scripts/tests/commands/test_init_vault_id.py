"""Per-command tests for `init --vault-id` (TASK 017 bead 017-08).

Locks:
- TC-UNIT-017-08-01: `init --root --vault-id <slug>` writes the field.
- TC-UNIT-017-08-02: `init --vault-id <slug>` without `--root` → exit 2.
- TC-UNIT-017-08-03: malformed slug → exit 24 BEFORE any I/O.
- TC-UNIT-017-08-04: idempotent re-run with SAME slug → no overwrite.
- TC-UNIT-017-08-05: re-run with DIFFERENT slug → exit 1, no overwrite.
- TC-UNIT-017-08-06: `init --root` (no `--vault-id`) preserves TASK 016 behaviour.
- TC-UNIT-017-08-07: round-trip with `read_vault_id`.
- TC-UNIT-017-08-08: validation happens BEFORE I/O on a non-existent target.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

from wiki_ingest import _safety
from wiki_ingest._vault import SCHEMA_FILE, read_vault_id
from wiki_ingest.commands import init as init_cmd


def _ns(**kwargs) -> argparse.Namespace:
    defaults = dict(root=False, dry_run=False, vault_id=None, cmd="init")
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


def _execute(args):
    """Run init.execute, capturing stdout/stderr; return (rc, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    try:
        with redirect_stdout(out), redirect_stderr(err):
            rc = init_cmd.execute(args)
    except SystemExit as exc:
        rc = int(exc.code or 0)
    return rc, out.getvalue(), err.getvalue()


def _sha256_dir(path: Path) -> str:
    """Aggregate sha256 of a directory's tree (sorted, content + path)."""
    h = hashlib.sha256()
    for p in sorted(path.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(path).as_posix().encode())
            h.update(b"\0")
            h.update(p.read_bytes())
            h.update(b"\0")
    return h.hexdigest()


class TestVaultIdFlagWithRoot(unittest.TestCase):
    """TC-UNIT-017-08-01 — happy path."""

    def test_happy_path_writes_slug(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, _, _ = _execute(_ns(
                vault=tmp, root=True, vault_id="trade-agents",
            ))
            self.assertEqual(rc, 0)
            schema = Path(tmp) / SCHEMA_FILE
            self.assertTrue(schema.is_file())
            text = schema.read_text(encoding="utf-8")
            self.assertIn("vault_id: trade-agents", text)
            # And the field lands AFTER `kind: vault-root` (deterministic position).
            kind_idx = text.find("kind: vault-root")
            vid_idx = text.find("vault_id: trade-agents")
            self.assertGreater(vid_idx, kind_idx,
                               "vault_id must follow kind: vault-root")


class TestVaultIdRequiresRoot(unittest.TestCase):
    """TC-UNIT-017-08-02."""

    def test_vault_id_without_root_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, _, stderr = _execute(_ns(
                vault=tmp, root=False, vault_id="trade-agents",
            ))
            self.assertEqual(rc, _safety.EXIT_USAGE)
            self.assertIn("--vault-id requires --root", stderr)
            # NO files written.
            self.assertEqual(list(Path(tmp).iterdir()), [])


class TestMalformedSlug(unittest.TestCase):
    """TC-UNIT-017-08-03 + TC-UNIT-017-08-08."""

    def test_malformed_slug_exits_24_before_io(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, _, stderr = _execute(_ns(
                vault=tmp, root=True, vault_id="1bad",
            ))
            self.assertEqual(rc, _safety.EXIT_INVALID_VAULT_ID)
            self.assertIn("INVALID_VAULT_ID", stderr)
            # No I/O — the target temp dir stays empty.
            self.assertEqual(list(Path(tmp).iterdir()), [])

    def test_malformed_slug_rejects_before_target_dir_check(self):
        """TC-UNIT-017-08-08 — validation order: slug check fires BEFORE
        `target directory does not exist`, so an invalid slug to a
        nonexistent vault still routes to exit 24 (not exit 1)."""
        rc, _, stderr = _execute(_ns(
            vault="/nonexistent/path/should-not-be-touched",
            root=True, vault_id="1bad",
        ))
        self.assertEqual(rc, _safety.EXIT_INVALID_VAULT_ID)
        self.assertIn("INVALID_VAULT_ID", stderr)


class TestIdempotentSameSlug(unittest.TestCase):
    """TC-UNIT-017-08-04."""

    def test_same_slug_rerun_is_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = _execute(_ns(vault=tmp, root=True, vault_id="trade-agents"))
            self.assertEqual(first[0], 0)
            digest1 = _sha256_dir(Path(tmp))
            second = _execute(_ns(vault=tmp, root=True, vault_id="trade-agents"))
            self.assertEqual(second[0], 0)
            digest2 = _sha256_dir(Path(tmp))
            self.assertEqual(digest1, digest2,
                             "idempotent re-run must NOT mutate the schema")


class TestMismatchedSlug(unittest.TestCase):
    """TC-UNIT-017-08-05."""

    def test_different_slug_rerun_exits_1_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            _execute(_ns(vault=tmp, root=True, vault_id="trade-agents"))
            digest1 = _sha256_dir(Path(tmp))
            rc, _, stderr = _execute(_ns(
                vault=tmp, root=True, vault_id="other-vault",
            ))
            self.assertEqual(rc, _safety.EXIT_GENERIC)
            self.assertIn("vault_id mismatch", stderr)
            digest2 = _sha256_dir(Path(tmp))
            self.assertEqual(digest1, digest2,
                             "mismatch must NOT silently overwrite")


class TestRootWithoutVaultIdUnchanged(unittest.TestCase):
    """TC-UNIT-017-08-06."""

    def test_init_root_no_vault_id_preserves_task016_behavior(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, _, _ = _execute(_ns(vault=tmp, root=True))
            self.assertEqual(rc, 0)
            text = (Path(tmp) / SCHEMA_FILE).read_text(encoding="utf-8")
            self.assertNotIn("vault_id:", text,
                             "no flag → no vault_id field (backwards compatible)")


class TestRoundTripWithReadVaultId(unittest.TestCase):
    """TC-UNIT-017-08-07."""

    def test_write_then_read_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            rc, _, _ = _execute(_ns(
                vault=tmp, root=True, vault_id="trade-agents",
            ))
            self.assertEqual(rc, 0)
            self.assertEqual(read_vault_id(Path(tmp)), "trade-agents")


if __name__ == "__main__":
    unittest.main()
