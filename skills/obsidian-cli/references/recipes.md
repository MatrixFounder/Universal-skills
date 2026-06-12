# Obsidian CLI — recipes (composed playbooks)

End-to-end playbooks composing the native CLI with the `wiki-ingest` toolchain.
**Conventions (binding):** every mutating command carries an explicit `path=` AND `vault=`
(the CLI defaults to the *active file* otherwise — SKILL.md targeting discipline); each
recipe ends with a **Coherence** step (wiki-ingest-managed vault) or an explicit *No
coherence step* with the reason; request `format=json` only where the command reference
says it is available.

**Placeholders** (the two systems name vaults differently — SKILL.md targeting):
- `<v>` — the **Obsidian vault NAME** (for `obsidian vault=<v> …`).
- `$VR` — the vault's **absolute root path**, e.g. `VR=$(obsidian vault=<v> vault info=path)`.
  This is also the `<vault>` argument every `wiki-ingest` subcommand takes.
Confirm identity once: `obsidian vaults verbose` path == the directory holding
`WIKI_SCHEMA.md`. If `WIKI_SCHEMA.md` is absent, the vault is not wiki-ingest-managed —
every Coherence step below self-disables (say so).

`wiki-ingest <sub>` is the PATH wrapper; `python3 <skills-repo>/skills/wiki-ingest/scripts/wiki_ops.py <sub>`
is the identical direct form.

---

## 1. Link-safe rename / move

**Goal:** rename or move a note without breaking inbound `[[wikilinks]]`.
**Preconditions:** CLI available (`obsidian help`); vault identity confirmed; in Obsidian,
*Settings → Files & Links → Automatically update internal links* is **ON** (verify once per
vault — without it the app does not rewrite backlinks). **Dogfood-verified failure mode
(2026-06-12, Obsidian 1.12.7):** with the setting OFF, `obsidian rename` renames the file
on disk but does NOT rewrite inbound links, and the CLI call BLOCKS (does not return)
waiting on the app side — in a non-interactive shell this hangs the turn with the vault
already mutated. If you cannot confirm the setting is ON, do not app-rename; bracket any
unavoidable rename with `wiki-ingest lint` before/after.
**HARD STOP:** the target is NOT under `_sources/`. Footnote tags `[^src-<slug>]` on
concept/entity pages are not links — the app will not rewrite them, and every citation of
that source silently desyncs. Decline a `_sources/` rename and explain; there is no safe
automated path.

```bash
# baseline (for the coherence proof)
wiki-ingest lint "$VR"                  # note orphan + dangling counts

# rename (app rewrites every inbound wikilink):
obsidian vault=<v> rename path="_concepts/Health.md" name="Wellbeing"
# OR move into another folder:
obsidian vault=<v> move path="Notes/raw-idea.md" to="Archive/raw-idea.md"
```

**Coherence:** only when the renamed/moved page lives under `_concepts/`/`_entities/`
(a non-wiki note is not cataloged in `index.md` — no step needed):
`wiki-ingest reindex "$VR"` — always a full rebuild from disk (no mtime-delta trap), so
`index.md` rows pick up the new path/slug. Then prove it:
```bash
wiki-ingest reindex "$VR"
wiki-ingest lint "$VR"        # orphan/dangling counts MUST equal the baseline
```
**Failure handling:** target name already exists → the CLI errors; report it verbatim and
propose a different name — never pass a force/overwrite flag to win a collision. If the
dangling count rose, the "update internal links" setting was off → restore from `history`
and re-run with it on.

---

## 2. Capture to the daily note

**Goal:** append a quick capture to today's daily note.
**Preconditions:** `obsidian help daily:append` confirms the Daily Notes plugin is enabled
(it is plugin-gated).

```bash
obsidian vault=<v> daily:append content="- [ ] call Anna tomorrow"
```
**No coherence step** — daily notes live outside the wiki dirs
(`_sources/_concepts/_entities`), and `index.md` catalogs wiki pages only.
**Failure handling:** `obsidian help daily:append` shows nothing → plugin disabled; either
ask the operator to enable Daily Notes, or compute the daily path from the plugin's
date format and `append path=<that path> content=…` instead.

---

## 3. Task sweep

**Goal:** find open tasks in a scope and mark some done.
**Preconditions:** CLI available.

```bash
obsidian vault=<v> tasks todo path="Projects/" format=json     # bounded scope + JSON
# for each task to close (ref is path:line from the JSON):
obsidian vault=<v> task ref="Projects/Alpha.md:42" done
```
**No coherence step** — a task toggle is a content change; `index.md` catalogs pages, not
content.
**Failure handling:** a `ref` whose line moved (file edited since the listing) → re-run
`tasks` to refresh refs before toggling; never toggle by stale line number.

---

## 4. Base → JSON → analysis

**Goal:** pull structured rows out of a Base and reason over them.
**Preconditions:** `obsidian help base:query` confirms Bases is enabled.

```bash
obsidian vault=<v> bases                                  # find the .base file
# base:views lists views of the CURRENT base (no path= param) — open the base to make it current:
obsidian vault=<v> open path="Projects.base"
obsidian vault=<v> base:views                             # view names of the now-current base
# base:query DOES take path= — query the target base directly:
obsidian vault=<v> base:query path="Projects.base" view="Overdue" format=json
```
Analyse the returned JSON in-context and answer; cite the query output, not training data.
**No mutation — no coherence step.**
**Failure handling:** unknown view → `open` the base then `base:views` (it reads the current
base only — it has no `path=`). Bases disabled → fall back to `wiki-ingest find "$VR"
--terms "<words>"` / plain file reads if the data is plain frontmatter; otherwise report
the gate.

---

## 5. Property migration

**Goal:** set/normalise a typed frontmatter property across a set of notes.
**Preconditions:** CLI available; know the target type (`text|list|number|checkbox|date|datetime`).

```bash
obsidian vault=<v> properties counts                      # survey current property usage
# per file (explicit path each time):
obsidian vault=<v> property:set path="Areas/Health.md" name="status" value="active" type="text"
```
**No coherence step** — frontmatter is content; `index.md` rows don't carry it. Optionally
`wiki-ingest log-event "$VR" --event property-migration --title "<what changed>"` if the
migration is worth the grep-trail.
**Failure handling:** wrong `type=` makes Obsidian store the value oddly → `property:read` to
verify, `property:remove` + re-set if needed. Batch carefully — one `property:set` per file,
each with its own `path=`.

---

## 6. History recovery

**Goal:** restore a clobbered note from local file recovery.
**Preconditions:** File Recovery has snapshots for the file (snapshots accrue on edit over
time; a brand-new note may have none).

```bash
obsidian vault=<v> history path="Notes/Important.md"            # list versions
obsidian vault=<v> history:read path="Notes/Important.md" version=2   # inspect the candidate
# SHOW the operator the version (or diff vs current) and get explicit confirmation, THEN:
obsidian vault=<v> history:restore path="Notes/Important.md" version=2
```
**Coherence:** none for a plain note (content change). If the restored file is a
`_concepts/`/`_entities/` page, run `wiki-ingest lint "$VR"` — the restored version may
resurrect dangling `[[links]]` or pre-date later footnotes; surface findings, don't auto-fix.
**Failure handling:** restore is destructive of the current content → in an autonomous run,
STOP after `history:read` and report options; never restore without showing the target
version first. No versions → report honestly; offer `sync:history`/`sync:restore` if Sync is
enabled.

---

## 7. Vault audit

**Goal:** cross-check the live link graph against the wiki-ingest view.
**Preconditions:** CLI available; vault is wiki-ingest-managed.

```bash
obsidian vault=<v> orphans total
obsidian vault=<v> deadends total
obsidian vault=<v> unresolved counts format=json
wiki-ingest lint "$VR"                                    # the wiki-layer view
```
Reconcile: the app counts links **live** across the whole vault; `wiki-ingest lint` checks
the wiki layer (orphan pages, dangling `[[links]]`, open contradictions, missing concept
pages — the latter two the app cannot see). An `index.md` that disagrees with disk →
`wiki-ingest reindex "$VR"` and re-compare.
**No mutation — no coherence step** (unless you reindex to reconcile, which is itself the
coherence action).
**Failure handling:** large `unresolved` list → use `format=json` + bounded review; a gap
that persists after `reindex` points to links outside the wiki dirs (the app counts them,
wiki-ingest doesn't) — explain the scope difference instead of chasing zero.

---

## 8. Workspace / session setup

**Goal:** arrange panes/tabs for a working session.
**Preconditions:** CLI available.

```bash
obsidian vault=<v> workspace                              # inspect current layout (T1)
obsidian vault=<v> open path="Dashboards/Today.md" newtab
obsidian vault=<v> tab:open file="Projects/Alpha.md"
```
These are T1/T1-UX (open/GUI state, no on-disk note change).
**No mutation — no coherence step.**
**Failure handling:** `workspace:save`/`workspace:load` are plugin-gated/doc-only on some
builds → feature-detect with `obsidian help workspace:save` before relying on them.
