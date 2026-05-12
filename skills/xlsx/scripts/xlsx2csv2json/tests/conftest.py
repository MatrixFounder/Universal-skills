"""Shared test scaffolding for the ``xlsx2csv2json`` package.

This file is intentionally empty in v1 — fixtures are loaded directly
inside individual test modules via ``Path(__file__).resolve().parent
/ "fixtures" / "<name>.xlsx"``. The placeholder keeps the directory
discoverable to ``unittest`` (so pytest-style autodiscovery does not
trip on a missing module) and gives later tasks (010-04 / 010-07) a
home for shared fixtures if the need arises.
"""
