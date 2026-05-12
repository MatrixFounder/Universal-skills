"""Shared fixture-path helper for xlsx_read tests.

Plain module (not a pytest conftest hook — tests use unittest); name
chosen for parity with xlsx-7 / xlsx-2 testing conventions.
"""

from pathlib import Path

FIXTURES_DIR: Path = Path(__file__).parent / "fixtures"
