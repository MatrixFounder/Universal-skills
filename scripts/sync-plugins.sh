#!/usr/bin/env bash
# Regenerate the plugins/ tree AND .claude-plugin/marketplace.json from skills/.
#
# Source of truth: skills/<name>/. For each skill there, generates:
#   plugins/<name>/.claude-plugin/plugin.json   — manifest (with curated
#                                                  human tagline + keywords)
#   plugins/<name>/skills/<name>                — relative symlink → ../../../skills/<name>
# And rewrites:
#   .claude-plugin/marketplace.json             — catalog of all generated plugins
#                                                  (preserves owner/metadata header)
#
# Run after adding/removing/renaming a skill. The script reconciles three
# layers and runs a drift check at the end so a missed sync fails fast
# instead of leaving a broken catalog.
#
# Why symlinks: per Claude Code docs (https://code.claude.com/docs/en/plugin-marketplaces)
# git-based marketplaces clone the entire repo, so a relative symlink to
# ../../../skills/<name> resolves correctly inside the user's local clone.
# Source of truth stays in skills/ — no duplication, no replication
# protocol breakage with CLAUDE.md §2.
#
# If you ever need to support marketplace transports OTHER than git clone
# (URL-based marketplace.json that fetches plugin files separately, or
# git-subdir sparse checkouts that fetch ONLY plugins/<name>/), switch
# the symlink line to `cp -R` so each plugin tree is self-contained. The
# tradeoff is doubled disk usage and a discipline burden (changes in
# skills/ won't propagate without re-running this script).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SKILLS_DIR="$REPO_ROOT/skills"
PLUGINS_DIR="$REPO_ROOT/plugins"
CATALOG="$REPO_ROOT/.claude-plugin/marketplace.json"

REPO_URL="https://github.com/MatrixFounder/Universal-skills"
MARKETPLACE_NAME="universal-skills"
AUTHOR_NAME="Sergey K."
AUTHOR_EMAIL="kuptsov.sergey@gmail.com"
VERSION="1.0.0"

if [ ! -d "$SKILLS_DIR" ]; then
    echo "ERROR: $SKILLS_DIR not found" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Per-skill curated metadata.
#
# Why curated, not auto-generated: SKILL.md `description:` is optimized for
# Claude's skill-routing trigger matching ("Use when... markdown to docx,
# docx to markdown, fill Word template..."). Reusing it as the plugin
# manifest description produces 300+ char trigger-phrase walls in the
# marketplace UI. We keep SKILL.md's triggers untouched (don't break
# routing) and curate a tight 1-line description here for human browsing.
# ---------------------------------------------------------------------------

# bash 4 associative arrays would be cleaner; macOS ships bash 3.2 so we
# use parallel-key lookups via a function.
metadata_for() {
    case "$1" in
        # Office skills
        docx) cat <<'EOF'
TAGLINE=Markdown↔docx round-trip + template fill + tracked-changes accept + deep XSD validator + msoffcrypto-tool encrypt/decrypt
CATEGORY=office
KEYWORDS=docx,word,office,ooxml,markdown,template,encryption
EOF
;;
        xlsx) cat <<'EOF'
TAGLINE=CSV→xlsx with styling + LibreOffice formula recalc + deep XlsxValidator + openpyxl charts + msoffcrypto-tool encrypt/decrypt
CATEGORY=office
KEYWORDS=xlsx,excel,office,ooxml,csv,chart,openpyxl,encryption
EOF
;;
        pptx) cat <<'EOF'
TAGLINE=Markdown→pptx (built-in or marp) + outline skeleton + orphan cleanup + deep PptxValidator + Cyrillic mermaid + encrypt/decrypt
CATEGORY=office
KEYWORDS=pptx,powerpoint,office,ooxml,marp,mermaid,thumbnails,encryption
EOF
;;
        pdf) cat <<'EOF'
TAGLINE=Markdown→PDF (weasyprint, Cyrillic mermaid) + pypdf merge/split + AcroForm fill (XFA detection) + PNG-grid preview
CATEGORY=office
KEYWORDS=pdf,weasyprint,pypdf,mermaid,acroform,merge,split
EOF
;;
        marp-slide) cat <<'EOF'
TAGLINE=Marp slides with 7 themes + custom themes + image layouts + mermaid preprocessing + editable PPTX export via LibreOffice
CATEGORY=office
KEYWORDS=marp,slides,presentation,mermaid,themes
EOF
;;

        # Meta-skills
        skill-creator) cat <<'EOF'
TAGLINE=Scaffold + upgrade + eval + benchmark agent skills against the Gold-Standard structural template
CATEGORY=meta
KEYWORDS=skill,meta,scaffolding,validation,gold-standard
EOF
;;
        skill-validator) cat <<'EOF'
TAGLINE=Audit a skill for security vulnerabilities (malicious bash, injection vectors) and Gold-Standard structural compliance
CATEGORY=meta
KEYWORDS=skill,meta,validation,security,audit
EOF
;;
        skill-enhancer) cat <<'EOF'
TAGLINE=Audit, fix, or improve an existing skill to meet Gold-Standard compliance
CATEGORY=meta
KEYWORDS=skill,meta,refactor,gold-standard
EOF
;;

        # Verification (VDD)
        vdd-adversarial) cat <<'EOF'
TAGLINE=Verification-Driven Development adversarial reviewer — destroys happy-path assumptions, finds edge cases the builder missed
CATEGORY=verification
KEYWORDS=vdd,verification,adversarial,code-review,qa
EOF
;;
        vdd-sarcastic) cat <<'EOF'
TAGLINE=VDD adversarial review with a sarcastic, provocative tone — exposes lazy patterns by being uncomfortable to read
CATEGORY=verification
KEYWORDS=vdd,verification,adversarial,code-review,tone
EOF
;;

        # Content
        post-writing) cat <<'EOF'
TAGLINE=Write, draft, or rewrite social-media posts (LinkedIn, Telegram, Blog) for higher engagement
CATEGORY=content
KEYWORDS=writing,social-media,linkedin,telegram,blog
EOF
;;
        text-humanizer) cat <<'EOF'
TAGLINE=Humanize AI-generated text or generate untraceable system prompts in multiple genres (Wiki, Creative, Crypto, etc.)
CATEGORY=content
KEYWORDS=text,humanize,rewriting,prompts
EOF
;;
        summarizing-meetings) cat <<'EOF'
TAGLINE=Auto-detects meeting type and produces a two-level pyramid Markdown summary optimized for people, AI agents, RAG, Obsidian
CATEGORY=content
KEYWORDS=meetings,summary,transcription,rag,obsidian
EOF
;;
        transcript-fetcher) cat <<'EOF'
TAGLINE=Fetch clean plain-text transcripts from video URLs (YouTube via yt-dlp) with manual→auto language fallback, rolling-caption dedup, >> speaker turns, and a JSON stat sidecar
CATEGORY=content
KEYWORDS=transcript,youtube,yt-dlp,vtt,subtitles,captions,fetcher
EOF
;;

        # Workflow
        brainstorming) cat <<'EOF'
TAGLINE=Open-ended exploration partner — brainstorm, clarify requirements, design architecture, generate options
CATEGORY=workflow
KEYWORDS=brainstorming,ideation,exploration,design
EOF
;;

        # Development
        mcp-builder) cat <<'EOF'
TAGLINE=Build production-quality MCP (Model Context Protocol) servers in Python (FastMCP) or Node/TypeScript (MCP SDK)
CATEGORY=development
KEYWORDS=mcp,model-context-protocol,server,fastmcp,typescript
EOF
;;
        hooks-creator) cat <<'EOF'
TAGLINE=Customize Gemini CLI behavior using hooks (events, blockers, loggers) with templates and patterns
CATEGORY=development
KEYWORDS=hooks,gemini,cli,automation
EOF
;;
        *) cat <<EOF
TAGLINE=Skill: $1
CATEGORY=other
KEYWORDS=skill
EOF
;;
    esac
}

# Office skills are Proprietary (per-skill LICENSE files); everything else
# inherits the root Apache-2.0 LICENSE.
license_for() {
    case "$1" in
        docx|xlsx|pptx|pdf) echo "LicenseRef-Proprietary" ;;
        *)                  echo "Apache-2.0" ;;
    esac
}

# Read a key=value line out of metadata_for() output.
get_meta() { metadata_for "$1" | grep "^$2=" | head -1 | cut -d= -f2-; }

mkdir -p "$PLUGINS_DIR"

# Marker baked into every generated plugin.json so cleanup can tell its own
# output apart from hand-curated plugins. A hand-curated plugin (without
# this marker) is NEVER touched by this script.
GENERATOR_TAG="sync-plugins.sh@universal-skills"

# ---------------------------------------------------------------------------
# Cleanup phase. Remove plugins/<name>/ ONLY if:
#   1. its plugin.json carries our $GENERATOR_TAG (i.e. WE created it on a
#      previous run — never touch hand-curated plugins), AND
#   2. there is no corresponding skills/<name>/ any more (the skill was
#      removed/renamed since the last sync).
# Both conditions together mean "this is our orphan and safe to delete".
# ---------------------------------------------------------------------------
removed=0
for p in "$PLUGINS_DIR"/*/; do
    [ -d "$p" ] || continue
    manifest="$p.claude-plugin/plugin.json"
    [ -f "$manifest" ] || continue
    name=$(basename "$p")
    # Skip hand-curated plugins (no generator tag).
    if ! python3 -c "
import json, sys
m = json.load(open(sys.argv[1]))
sys.exit(0 if m.get('_generator') == sys.argv[2] else 1)
" "$manifest" "$GENERATOR_TAG" 2>/dev/null; then
        echo "  keep: plugins/$name/ (hand-curated; no generator tag)"
        continue
    fi
    if [ ! -d "$SKILLS_DIR/$name" ]; then
        rm -rf "$p"
        echo "  removed: plugins/$name/ (orphan — skills/$name no longer exists)"
        removed=$((removed + 1))
    fi
done

# ---------------------------------------------------------------------------
# Generate one plugin per skill.
# ---------------------------------------------------------------------------
count=0
PLUGIN_NAMES=()
for skill_dir in "$SKILLS_DIR"/*/; do
    skill_name=$(basename "$skill_dir")
    [ -f "$skill_dir/SKILL.md" ] || {
        echo "  skip: $skill_name (no SKILL.md)" >&2
        continue
    }

    plugin_dir="$PLUGINS_DIR/$skill_name"
    mkdir -p "$plugin_dir/.claude-plugin" "$plugin_dir/skills"

    # Symlink the skill content into the plugin's skills/ tree.
    # Relative target so the symlink survives a git clone unchanged.
    ln -snf "../../../skills/$skill_name" "$plugin_dir/skills/$skill_name"

    tagline=$(get_meta "$skill_name" TAGLINE)
    category=$(get_meta "$skill_name" CATEGORY)
    keywords_csv=$(get_meta "$skill_name" KEYWORDS)
    license=$(license_for "$skill_name")

    python3 - "$plugin_dir/.claude-plugin/plugin.json" "$skill_name" \
                "$tagline" "$category" "$keywords_csv" "$license" \
                "$REPO_URL" "$AUTHOR_NAME" "$AUTHOR_EMAIL" "$VERSION" \
                "$GENERATOR_TAG" <<'PY'
import json, sys
out, name, tagline, category, keywords_csv, lic, repo, an, ae, version, gen = sys.argv[1:]
keywords = [k.strip() for k in keywords_csv.split(",") if k.strip()]
manifest = {
    "name": name,
    "version": version,
    "description": tagline,
    "author": {"name": an, "email": ae},
    "homepage": repo,
    "repository": repo,
    "license": lic,
    "keywords": keywords,
    "category": category,
    # Marker so sync-plugins.sh can distinguish its own output from
    # hand-curated plugins. Don't remove — the cleanup loop relies on it
    # to avoid silently deleting a manually-added plugin.
    "_generator": gen,
}
with open(out, "w") as f:
    json.dump(manifest, f, indent=2, ensure_ascii=False)
    f.write("\n")
PY

    PLUGIN_NAMES+=("$skill_name")
    count=$((count + 1))
    printf "  ok:  plugins/%-25s license=%-22s category=%s\n" \
        "$skill_name" "$license" "$category"
done

# ---------------------------------------------------------------------------
# Regenerate marketplace.json so it always reflects the current set of
# generated plugins. Owner block, metadata.description, and metadata.version
# are constants here (intentional — bump $VERSION at top of script). This
# rules out the "renamed-skill leaves orphan in catalog" drift class.
# ---------------------------------------------------------------------------
python3 - "$CATALOG" "$MARKETPLACE_NAME" "$AUTHOR_NAME" "$AUTHOR_EMAIL" \
            "$REPO_URL" "$VERSION" "$PLUGINS_DIR" "${PLUGIN_NAMES[@]}" <<'PY'
import json, sys, os
out, name, an, ae, repo, version, plugins_dir, *plugin_names = sys.argv[1:]
plugins = []
for pname in plugin_names:
    manifest_path = os.path.join(plugins_dir, pname, ".claude-plugin", "plugin.json")
    with open(manifest_path) as f:
        m = json.load(f)
    plugins.append({
        "name": pname,
        "source": pname,                  # resolved against metadata.pluginRoot
        "description": m["description"],  # mirror plugin.json tagline
        "category": m["category"],
        "tags": m["keywords"],            # `tags` is a marketplace-specific
                                          # field per the docs; mirror keywords
                                          # so search picks up either.
    })
catalog = {
    "name": name,
    "owner": {
        "name": an,
        "email": ae,
        "url": "https://github.com/MatrixFounder",
    },
    "metadata": {
        "description": (
            "Universal-Skills marketplace: agent-agnostic skills for Claude "
            "Code. Pick and install only the skills you need — office "
            "(docx/xlsx/pptx/pdf), presentations (marp-slide), meta-skills "
            "(skill-creator/validator/enhancer), VDD verification, content "
            "writing, and more."
        ),
        "version": version,
        "pluginRoot": "./plugins",   # plugins[].source resolves against this,
                                     # so we can write "docx" instead of
                                     # "./plugins/docx" (per docs § Required
                                     # fields → metadata.pluginRoot).
    },
    "plugins": plugins,
}
with open(out, "w") as f:
    json.dump(catalog, f, indent=2, ensure_ascii=False)
    f.write("\n")
PY

# ---------------------------------------------------------------------------
# Drift check. Every generated plugin must have a corresponding entry in
# marketplace.json, and every marketplace.json entry's source must resolve
# to a real directory. Fail fast if either invariant is violated — this
# catches the "forgot to re-run sync after editing one file" class.
# ---------------------------------------------------------------------------
python3 - "$CATALOG" "$PLUGINS_DIR" "$REPO_ROOT" <<'PY'
import json, os, sys
catalog_path, plugins_dir, repo_root = sys.argv[1:]
catalog = json.load(open(catalog_path))
plugin_root = catalog.get("metadata", {}).get("pluginRoot", "").lstrip("./")
catalog_names = {p["name"] for p in catalog["plugins"]}
disk_names = {
    d for d in os.listdir(plugins_dir)
    if os.path.isfile(os.path.join(plugins_dir, d, ".claude-plugin", "plugin.json"))
}
missing_in_catalog = sorted(disk_names - catalog_names)
missing_on_disk = sorted(catalog_names - disk_names)
broken_sources = []
for p in catalog["plugins"]:
    rel = p["source"]
    if not rel.startswith("./") and not rel.startswith("/") and plugin_root:
        rel = os.path.join(plugin_root, rel)
    full = os.path.join(repo_root, rel)
    if not os.path.isdir(full):
        broken_sources.append(f"{p['name']}: source={p['source']} → {full} (not a dir)")
problems = []
if missing_in_catalog:
    problems.append(f"on disk but missing from marketplace.json: {missing_in_catalog}")
if missing_on_disk:
    problems.append(f"in marketplace.json but missing on disk: {missing_on_disk}")
if broken_sources:
    problems.append("broken sources:\n  " + "\n  ".join(broken_sources))
if problems:
    print("\nDRIFT DETECTED:", file=sys.stderr)
    for prob in problems:
        print(f"  - {prob}", file=sys.stderr)
    sys.exit(1)
print(f"\nDrift check: OK ({len(catalog_names)} plugins consistent across disk and catalog)")
PY

echo
[ "$removed" -gt 0 ] && echo "Cleaned up $removed orphaned plugin(s)."
echo "Generated $count plugins."
echo "Catalog:  $CATALOG"
echo "Plugins:  $PLUGINS_DIR"
