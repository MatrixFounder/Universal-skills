# Folder Ingest Workflow

When a source isn't a single file but a **folder** (or a multi-file bundle), the agent's job is to:

1. **Discover** all files
2. **Group** them logically (one summary per group, not per file)
3. **Classify** each file's role within its group (primary / metadata / merge / link)
4. **Generate** one primary summary per group, with companion-material links
5. **Ingest** each summary through the standard wiki-ingest cycle

This is the **Phase 0** that runs BEFORE the regular ingest pipeline when input is a folder.

## When to use

- Input path is a directory containing multiple related files
- A "lesson" / "session" / "module" comprises a transcript + slides + notes + recipe-files
- Operator says "ingest this folder" / "process this course" / "import this lesson bundle"

If input is a single file → skip this entire workflow; go straight to standard ingest.

## The algorithm (5 phases)

### Phase 0a — Grouping pattern detection

Detect HOW files should be grouped within the folder. Three patterns, in priority order:

**Pattern 1: filename-prefix (`NN -`, `NN.M-`, `NN_`, etc.)**
```
01 - intro.md
01 - intro - slides.pptx
02 - main process.txt
03 - implementation phase.md
03 - specification_template.docx
03 - ricef.txt
```
Group key = leading numeric prefix. Each lesson = one group.

**Pattern 2: sibling-sidecar (`<base>.<sidecar>.<ext>`)**
```
lesson.txt
lesson.description.md
lesson.txt.stat.json
```
Group key = shared base before first `.`. Entire folder = one group with multiple roles.

**Pattern 3: flat (no detectable pattern)**
Whole folder treated as a single group.

Detection: try Pattern 1 (≥50% match), then Pattern 2 (≥1 base with ≥2 files covering ≥50%), then default to flat.

**Operator override**: `wiki_ops.py classify-folder <path> --group-by '<regex with capture>'` to force a custom grouping pattern.

### Phase 0b — Per-file classification

For each file in a group, assign one of 5 roles:

| Role | What it is | Examples | What ingest does with it |
|---|---|---|---|
| **`primary`** | Main content to summarise | `lesson.txt`, `01 - intro.md` | Passed to `summarizing-meetings` as primary source |
| **`metadata`** | Structured data for frontmatter, not summarised | `lesson.txt.stat.json`, `talk.metadata.yaml` | Fields extracted into summary's frontmatter |
| **`merge`** | Supplementary notes that enrich the primary summary | `talk.notes.md`, `03 - ricef.txt` (small flat) | Included in `summarizing-meetings` prompt as additional context |
| **`link`** | Standalone artifact: referenced from summary but NOT copied | `lesson.description.md` (full install prompt), `slides.pptx`, `template.docx` | Added to `companion_links:` frontmatter + `## Companion Material` body section; NEVER copied into the wiki |
| **`derived-output`** | Previously-generated summary, not a source | `summary.md` with `type: lesson-summary` frontmatter | **Skipped** from ingest entirely |

**Classification rules** (in priority order):

1. **Skip first**: hidden files (`.DS_Store`, dotfiles), `.lock`, `.swp`, `.pyc`
2. **Extension-based**:
   - `.docx`, `.pptx`, `.xlsx`, `.pdf` → always `link` (binary, can't inline)
   - `.png`, `.jpg`, `.gif`, `.svg`, `.webp`, `.bmp` → always `link` (asset)
   - `.json`, `.yaml`, `.yml`, `.toml`: if <4KB → `metadata`; else `link`
3. **Output detection** for text files: filename matches `^(summary|output|result|generated|_?wiki|index|log)` AND content has `type: lesson-summary` / `kind: source` frontmatter → `derived-output` (skip)
4. **Text-readable** (`.txt`, `.md`, `.markdown`, `.rst`) → "text-candidate" (provisional, resolved per-group)
5. **Other** extensions → `link` by default

### Phase 0c — Primary selection within group

After per-file classification, each group has 0, 1, or N text-candidates.

- **0 candidates** → warn ("no text-readable primary; consider running an extraction skill on a binary first"); skip the group OR ask operator
- **1 candidate** → that file is automatically primary (regardless of size/structure)
- **≥2 candidates** → use scoring:
  1. **Segment-aware filename hint score**: split stem on `.`/`-`/`_`/whitespace; check each segment against primary/non-primary hint lists; right-most segment weighted 3x
     - Primary hints: `transcript`, `main`, `content`, `intro`, `lesson`, `phase`, `recording`, `talk`, `session`
     - Non-primary hints: `slides`, `notes`, `template`, `appendix`, `specification`, `spec`, `ricef`, `glossary`, `cheatsheet`, `outline`, `agenda`, `description`, `metadata`
  2. **Pool filter**: if some files have positive hint AND others negative → only non-negative files compete (hint wins categorically)
  3. **Within pool**: pick by `log10(size) * 10 + hint + 5 (if prose) ` 
  4. **Tie-break review**: if top vs runner-up differ by <5 points, flag for operator review

**Why hint outranks size**: a 90KB `lesson.description.md` is bigger than an 18KB `lesson.txt`, but the hint "description" is a non-primary signal — the 18KB transcript is genuinely the primary content. The pool-filter handles this categorically.

**Unchosen text-candidates** (from ≥2 case) get demoted:
- ≥2KB AND ≥3 `## headings` AND ≥2 fence-lines → `link` (looks standalone)
- <5KB AND <2 `## headings` → `merge` (looks supplementary)
- Otherwise → `link` (default)

### Phase 0d — Emit plan

`classify-folder` returns JSON with:
- `source_folder`: absolute path
- `grouping`: `{pattern: "prefix"|"sibling"|"flat", info: {...}}`
- `groups`: list of `{group_key, files: {primary, metadata, merge, link}, derived_outputs, skipped, rationale, warnings}`

The agent **reviews this plan** with the operator before proceeding to ingest.

### Phase 0e — Execute per-group ingest

For each group:

1. **Invoke `summarizing-meetings`** with:
   - Source: contents of `primary` file
   - Context: contents of `merge` files appended as additional sections
   - Known-concepts list: from `wiki_ops.py scan`
   - Target: `<vault>/_sources/<slug>.md`

2. **Post-process the generated summary**:
   - Inject `companion_links:` field into frontmatter:
     ```yaml
     companion_links:
       - path: <relative or absolute path to link file>
         kind: <office-template | slides | recipe | asset | ...>
         description: <one-line description>
     ```
   - Extract `metadata` files' contents into frontmatter (`source_url`, `duration`, `embed_url`, etc.)
   - Append `## Companion Material` section to body with one bullet per link file (path + one-line description)

3. **Cross-group references** (bonus, for prefix-grouped folders):
   - Set `course: <folder name>`
   - Set `lesson_number: <group_key>`
   - Set `previous: [[<prev-group-slug>]]` / `next: [[<next-group-slug>]]` based on sort order

4. **Standard wiki-ingest cycle**: `register-summary` (if generated as file) OR run upserts directly → `update-index` → `append-log`

## Worked examples

### Example A: ZeroOne sibling pattern (transcript-fetcher output)

Folder: `Lessons/ZeroOne Systems/I Built a Zero-Human Trading Team with Claude/`
Files: `lesson.txt` (18K), `lesson.description.md` (90K), `lesson.txt.stat.json` (1K)

```
classify-folder output:
  pattern: sibling
  group 'lesson':
    primary: lesson.txt
    link: lesson.description.md
    metadata: lesson.txt.stat.json
```

Rationale: pool-filter dropped `lesson.description.md` despite being 5x bigger because "description" is a non-primary hint while "lesson" is a primary hint.

Ingest result:
- `_sources/zero-human-trading-team-claude.md` generated from lesson.txt
- frontmatter: `companion_links: [{path: ".../lesson.description.md", kind: installation-recipe}]`
- frontmatter: extracts `url`, `duration_sec` from `lesson.txt.stat.json`
- body: `## Companion Material` section with link to description.md
- description.md NOT copied (lives in raw folder)

### Example B: Prefix-grouped course

Folder contents: `01 - intro.md`, `01 - intro - slides.pptx`, `02 - main process.txt`, `03 - implementation phase.md`, `03 - specification_template.docx`, `03 - ricef.txt`

```
classify-folder output:
  pattern: prefix (matched 6/6)
  group '01': primary=01 - intro.md, link=[01 - intro - slides.pptx]
  group '02': primary=02 - main process.txt
  group '03': primary=03 - implementation phase.md, merge=[03 - ricef.txt], link=[03 - specification_template.docx]
```

Each group → its own summary in `_sources/`. Group 03's summary includes ricef text as supplementary context AND links to specification_template.docx without copying it.

Optional cross-references:
- 01's summary → `next: [[02-main-process]]`
- 02's summary → `previous: [[01-intro]]`, `next: [[03-implementation-phase]]`
- 03's summary → `previous: [[02-main-process]]`

### Example C: Single text-candidate small file

Folder: `quick-notes/`, contents: `meeting.md` (300B, no headings).

Without the "single text-candidate is primary regardless of size" rule, the heuristic would mis-classify it as `merge` (small/flat) and leave the group with no primary. The rule explicitly handles this case: ONE text-candidate in a group → primary, full stop.

## Edge cases

| Case | Algorithm response |
|---|---|
| Group with only binary files (.docx + .pptx, no text) | `warnings: ["no text-readable primary"]`; operator can run a converter first or skip the group |
| Two same-size .md files with no discriminating hint | Tie-break flag: `"close runner-up X — review"` in rationale; operator picks |
| Folder with `summary.md` from a previous ingest | Detected as `derived-output` by filename + frontmatter check; skipped from ingest plan |
| Nested folders (folder of folders) | Treat each subfolder as its own ingest target; iterate at the level above |
| Mixed pattern (some files have prefix, some don't) | Pattern detection picks prefix if ≥50% match; ungrouped files go into `_ungrouped` key for operator review |
| Operator wants different grouping | `--group-by '<regex>'` with one capture group |

## Anti-patterns

| Anti-pattern | Why wrong |
|---|---|
| Copy `link`-classified files into the wiki | Violates Karpathy's "raw is immutable" — wiki should only LINK, never duplicate |
| Generate a separate summary for every binary file in a group | Wasteful; `link` role exists precisely so binaries are referenced without summarisation |
| Skip the per-group plan and just summarise everything together | Loses logical structure of multi-lesson folders; produces one mega-summary instead of N targeted ones |
| Treat `metadata` files (JSON sidecars) as `merge` | Metadata is structured data for frontmatter, not prose to summarise |

## Where the logic lives

- **`scripts/wiki_ops.py classify-folder <path> [--group-by <regex>]`**: deterministic discovery + classification → JSON plan. No LLM judgement.
- **Agent (Phase 0 of SKILL.md ingest)**: reads the plan, may override roles via operator dialogue, then drives the per-group ingest using existing skill commands.
- **`summarizing-meetings`**: stays pipeline-agnostic. Doesn't know about sidecars or folder structure. Just summarises whatever sources it's given.
