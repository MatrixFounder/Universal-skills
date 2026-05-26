"""Internal package for the wiki-ingest skill.

Status (as of bead 015-01): only `_safety.py` is realised. The remaining
modules below land in beads 015-02..015-11; until then their symbols
still live in `wiki_ops.py` behind back-compat re-exports.

Layered model (one-way dependency rule, F3 → F2 → F1):

    F3 · Vault & Command Layer
        commands/*.py     (one CLI subcommand per module)
        _vault.py         (vault layout constants + walk + tail_log)
        _classify.py      (classify-folder helpers)

    F2 · Markdown / Frontmatter Engine
        _markdown.py      (section / wikilink / masking primitives)
        _frontmatter.py   (YAML split + structural splice)

    F1 · Safety & I/O Primitives
        _safety.py        (atomic I/O · NFKC · safe_inline · safe_for_json)

Rules:
- No command imports another command.
- No `_<helper>` module imports `commands/`.
- The package has NO public API; the only stable surface is the
  `wiki_ops.py` CLI shim (see SKILL.md for the agent contract).

Tests live in ../tests/.
"""
