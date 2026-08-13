# fixture-obsidian-vault

A minimal Obsidian vault used by `scripts/tests/test_obsidian2md.py` (TASK 030).

| Path | Why it exists |
|---|---|
| `.obsidian/app.json` | `attachmentFolderPath: ./_attachments` — R5(a), the note-relative form |
| `note.md` | exercises every FR: embeds, size hints, wikilinks, callouts, minor syntax, inert code regions, a mid-body `---` |
| `linked note.md` | transclusion target; embeds `note.md` back, so A9 (mutual transclusion) terminates |
| `folder/plain-target.md` | target for `[[folder/plain-target]]` — R4(b) last-segment rule |
| `plain-commonmark.md` | A10 — must pass through byte-identical |
| `_attachments/diagram.png` | 400×300, wider than A13's 120 px hint so the hint is a downscale |
| `_attachments/photo.jpg` | 200×150, the `100x50` two-dimension hint |
| `_attachments/100% coverage.png` | A16 — a literal `%` forces percent-encoding, because `decodeURI` throws on a bare one |
| `sub dir with space/nested.png` | D4 regression — resolved through the vault-wide index, path carries a space |

`missing-attachment.png`, `report.pdf` and `recording.mp3` are referenced but deliberately absent
or non-image: they drive A5 (placeholder + warning), A6 (`--strict-assets` exit 8) and R3(d).
