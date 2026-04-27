"""Shared fixtures for property-based tests (q-5).

Resolves per-skill venv pythons and CLI script paths. Each test module
talks to the CLIs as black boxes via subprocess — we do NOT import skill
code directly, since each skill's .venv has its own dependency closure.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SKILLS = ROOT / "skills"


def _skill_python(skill: str) -> Path:
    py = SKILLS / skill / "scripts" / ".venv" / "bin" / "python"
    if not py.is_file():
        pytest.skip(
            f"{skill} skill venv not found at {py}; run "
            f"skills/{skill}/scripts/install.sh first"
        )
    return py


def _node_bin() -> str:
    found = shutil.which("node")
    if found is None:
        pytest.skip("node not on PATH; install Node.js to run JS-based fuzzers")
    return found


@pytest.fixture(scope="session")
def docx_node() -> str:
    return _node_bin()


@pytest.fixture(scope="session")
def docx_md2docx_js() -> Path:
    return SKILLS / "docx" / "scripts" / "md2docx.js"


@pytest.fixture(scope="session")
def pdf_python() -> Path:
    return _skill_python("pdf")


@pytest.fixture(scope="session")
def pdf_md2pdf_py() -> Path:
    return SKILLS / "pdf" / "scripts" / "md2pdf.py"


@pytest.fixture(scope="session")
def xlsx_python() -> Path:
    return _skill_python("xlsx")


@pytest.fixture(scope="session")
def xlsx_csv2xlsx_py() -> Path:
    return SKILLS / "xlsx" / "scripts" / "csv2xlsx.py"


def pytest_configure(config: pytest.Config) -> None:
    """Surface env knobs the fuzzers respect.

    HYPOTHESIS_PROFILE=ci    → 100 examples per test (default 30 locally)
    """
    from hypothesis import HealthCheck, settings

    settings.register_profile("dev", max_examples=30, deadline=20_000,
                              suppress_health_check=[HealthCheck.too_slow])
    settings.register_profile("ci", max_examples=100, deadline=30_000,
                              suppress_health_check=[HealthCheck.too_slow])
    profile = os.environ.get("HYPOTHESIS_PROFILE", "dev")
    settings.load_profile(profile)
