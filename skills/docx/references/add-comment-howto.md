# Verifying `docx_add_comment.py`

A practical checklist for confirming the comment-insertion script
works end-to-end on a real `.docx`. Use it after install, after a
patch, or when a user reports "comments aren't showing up in Word".

> Script: [`skills/docx/scripts/docx_add_comment.py`](../scripts/docx_add_comment.py)
> Auto-tests: 8 checks in [`scripts/tests/test_e2e.sh`](../scripts/tests/test_e2e.sh) (`docx-1` block)

---

## 1. Prerequisites

```bash
cd skills/docx/scripts
bash install.sh                  # creates .venv + node_modules
ls .venv/bin/python              # must exist
```

The script needs only Python (no Node, no LibreOffice — pure XML
edit on the unpacked tree).

---

## 2. Quick smoke (60 seconds)

```bash
PY=skills/docx/scripts/.venv/bin/python

# Generate a fresh fixture, insert one comment, validate the result.
node skills/docx/scripts/md2docx.js skills/docx/examples/fixture-simple.md /tmp/in.docx

"$PY" skills/docx/scripts/docx_add_comment.py \
    /tmp/in.docx /tmp/out.docx \
    --anchor-text "Quarterly" \
    --comment "Please verify this number against the source data" \
    --author "QA Bot"

# Expected stdout (one line):
#   /tmp/out.docx: added 1 comment(s) (anchor='Quarterly', author='QA Bot')

# Validate the output structurally.
cd skills/docx/scripts && ./.venv/bin/python -m office.validate /tmp/out.docx
# Expected: "OK" (no warnings or errors).
```

If the smoke fails, see §6 below.

---

## 3. What got inserted (XML walkthrough)

The script touches **seven** OOXML parts (four core + three Word-2016+
side-parts that get auto-wired so future replies can thread). Inspect
each to confirm:

```bash
PY=skills/docx/scripts/.venv/bin/python

# 3a. word/comments.xml — the comment body itself
"$PY" -c "
import zipfile
with zipfile.ZipFile('/tmp/out.docx') as z:
    print(z.read('word/comments.xml').decode())
"
# Expected: a <w:comment w:id="N" w:author="QA Bot" w:initials="QB"
# w:date="..."> element with the body text inside <w:p>/<w:r>/<w:t>.

# 3b. word/document.xml — the inline anchor markers
"$PY" -c "
import zipfile, re
with zipfile.ZipFile('/tmp/out.docx') as z:
    doc = z.read('word/document.xml').decode()
print('commentRangeStart count:', len(re.findall(r'<w:commentRangeStart', doc)))
print('commentRangeEnd count:  ', len(re.findall(r'<w:commentRangeEnd', doc)))
print('commentReference count: ', len(re.findall(r'<w:commentReference', doc)))
"
# Expected: all three counts equal — one of each per added comment.
# (If only RangeStart is N but End is 0, the script is broken; file a
# bug.)

# 3c. word/_rels/document.xml.rels — relationship to comments.xml
"$PY" -c "
import zipfile
with zipfile.ZipFile('/tmp/out.docx') as z:
    rels = z.read('word/_rels/document.xml.rels').decode()
import re
hits = re.findall(r'<Relationship[^/]*Type=\"[^\"]*comments\"[^/]*/>', rels)
print('comments relationships:', len(hits))
print(hits[0] if hits else '(none)')
"
# Expected: at least one relationship of Type=".../relationships/comments"
# pointing at Target="comments.xml".

# 3d. [Content_Types].xml — Override for /word/comments.xml
"$PY" -c "
import zipfile, re
with zipfile.ZipFile('/tmp/out.docx') as z:
    ct = z.read('[Content_Types].xml').decode()
hits = [m for m in re.findall(r'<Override[^/]*/>', ct) if '/word/comments.xml' in m]
print('Override entries for /word/comments.xml:', len(hits))
print(hits[0] if hits else '(none)')
"
# Expected: exactly one Override with
# ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml".
```

If any of the four counts is wrong, the comment will not show up
in Word — Word silently drops orphan parts.

```bash
# 3e. word/commentsExtended.xml — paraId / paraIdParent threading
"$PY" -c "
import zipfile
with zipfile.ZipFile('/tmp/out.docx') as z:
    print(z.read('word/commentsExtended.xml').decode())
"
# Expected: a <w15:commentEx w15:paraId="HEX" w15:done="0"/> per top-
# level comment. Replies (added via --parent) carry an additional
# w15:paraIdParent="HEX" pointing at the parent's paraId.

# 3f. word/commentsIds.xml + commentsExtensible.xml — Word 2016+
# durable IDs, opaque to readers but required for round-tripping
# threaded conversations through Word's review pane.
"$PY" -c "
import zipfile
with zipfile.ZipFile('/tmp/out.docx') as z:
    print(z.read('word/commentsIds.xml').decode())
    print(z.read('word/commentsExtensible.xml').decode())
"
# Expected: one <w16cid:commentId> and one <w16cex:commentExtensible>
# per added comment, including replies.
```

---

## 4. Visual verification in Word / LibreOffice

```bash
# Render the file via LibreOffice headless to a PDF preview.
soffice --headless --convert-to pdf --outdir /tmp /tmp/out.docx

# Or use the bundled previewer for a one-page JPEG grid.
"$PY" skills/docx/scripts/preview.py /tmp/out.docx /tmp/out.jpg --dpi 110
open /tmp/out.jpg          # macOS; xdg-open on Linux
```

In the rendered output you should see a **speech-bubble icon**
next to the anchored text (`"Quarterly"` in the smoke). Open the
file in Microsoft Word or LibreOffice Writer and switch to
**Review → Show Comments** — the comment body and author should
appear in the side panel.

---

## 5. Edge cases worth running by hand

```bash
PY=skills/docx/scripts/.venv/bin/python

# 5a. --all on multiple matches across paragraphs AND within one paragraph
echo '# Multi
The cat saw the dog and the bird in the same garden.

The other paragraph also mentions the topic.' > /tmp/multi.md
node skills/docx/scripts/md2docx.js /tmp/multi.md /tmp/multi.docx

"$PY" skills/docx/scripts/docx_add_comment.py /tmp/multi.docx /tmp/multi-out.docx \
    --anchor-text "the" --comment "x" --author "Q" --all

"$PY" -c "
import zipfile, re
with zipfile.ZipFile('/tmp/multi-out.docx') as z:
    print('comments:', len(re.findall(r'<w:comment ', z.read('word/comments.xml').decode())))
"
# Expected: a number ≥ 5 — every lowercase 'the' across the document
# (if it returns 1 or 2, run-merging or intra-paragraph scan is broken).

# 5b. Anchor not found — should exit 2 with AnchorNotFound envelope
"$PY" skills/docx/scripts/docx_add_comment.py /tmp/in.docx /tmp/_x.docx \
    --anchor-text "ZZZNOTPRESENTZZZ" --comment "x" --json-errors
echo "exit=$?"
# Expected: exit 2; stderr is one-line JSON with "type":"AnchorNotFound".

# 5c. Same-path I/O — must refuse with exit 6
cp /tmp/in.docx /tmp/inplace.docx
"$PY" skills/docx/scripts/docx_add_comment.py /tmp/inplace.docx /tmp/inplace.docx \
    --anchor-text "Quarterly" --comment "x" --author "Q"
echo "exit=$?"
ls -la /tmp/inplace.docx
# Expected: exit 6 (SelfOverwriteRefused); /tmp/inplace.docx unchanged.

# 5d. Encrypted input — must refuse with exit 3
"$PY" -c "
from pathlib import Path
Path('/tmp/cfb.docx').write_bytes(b'\\xd0\\xcf\\x11\\xe0\\xa1\\xb1\\x1a\\xe1' + b'\\x00'*100)
"
"$PY" skills/docx/scripts/docx_add_comment.py /tmp/cfb.docx /tmp/_y.docx \
    --anchor-text "anything" --comment "x" 2>&1 | tail -1
echo "exit=$?"
# Expected: exit 3; message names "password-protected" and "legacy".

# 5e. Reply to an existing comment (threads in Word's review pane)
"$PY" skills/docx/scripts/docx_add_comment.py /tmp/in.docx /tmp/parent.docx \
    --anchor-text "Quarterly" --comment "verify" --author "QA"
"$PY" skills/docx/scripts/docx_add_comment.py /tmp/parent.docx /tmp/reply.docx \
    --parent 0 --comment "Acknowledged, fixing." --author "Dev"

"$PY" -c "
import zipfile, re
with zipfile.ZipFile('/tmp/reply.docx') as z:
    cx = z.read('word/comments.xml').decode()
    ext = z.read('word/commentsExtended.xml').decode()
print('comments:', len(re.findall(r'<w:comment ', cx)))
print('paraIdParent linkage:', 'paraIdParent' in ext)
"
# Expected: 'comments: 2', 'paraIdParent linkage: True'.
# In Word: open /tmp/reply.docx → Review → Show Comments — the second
# comment renders as a reply nested under the first.

# 5f. Library mode (in-place edit over an unpacked tree)
"$PY" -c "
from office.unpack import unpack
from pathlib import Path
unpack(Path('/tmp/in.docx'), Path('/tmp/lib_tree'))
"
"$PY" skills/docx/scripts/docx_add_comment.py --unpacked-dir /tmp/lib_tree \
    --anchor-text "Quarterly" --comment "lib comment" --author "QA"
"$PY" skills/docx/scripts/docx_add_comment.py --unpacked-dir /tmp/lib_tree \
    --parent 0 --comment "lib reply" --author "Dev"
"$PY" -c "
from office.pack import pack
from pathlib import Path
pack(Path('/tmp/lib_tree'), Path('/tmp/lib.docx'))
"
"$PY" -m office.validate /tmp/lib.docx
# Expected: 'OK'. Library mode is useful when chaining several edits
# (e.g., template-fill + comment + comment-reply) on a single unpacked
# tree — it skips repeated unpack/pack and the encryption check.
```

---

## 6. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Exit 2, `AnchorNotFound` JSON envelope. | Anchor doesn't exist in any paragraph, OR the anchor crosses a formatting boundary (mixed bold + plain) so adjacent-run merge can't reunite it into a single `<w:t>`. | Pick a shorter / more uniform substring. The merge pass joins adjacent runs that share `<w:rPr>`; a span like `**bold** plain` won't merge. |
| Exit 3 with "password-protected or legacy CFB". | Input is an encrypted Office file (CFB container). | Decrypt first via [`office_passwd.py`](../scripts/office_passwd.py) — `--decrypt PASSWORD` then re-feed the result. |
| Exit 6 `SelfOverwriteRefused`. | INPUT and OUTPUT resolve to the same file (literal match or symlink → same inode). | Use a distinct OUTPUT path. The guard mirrors `office_passwd.py`'s cross-7 H1 protection. |
| Comment appears in `comments.xml` but not in Word's review pane. | Missing relationship or missing Content_Types Override. Either an upstream copy of the file stripped them, or `_ensure_relationship` / `_ensure_content_type` failed silently. | Re-run §3c and §3d above; both should report exactly one matching entry. If they don't, repack the file via `office.unpack` → `office.pack`. |
| Anchor matched once when expected N times under `--all`. | `_wrap_anchors_in_paragraph` regression (one of the VDD-fix paths broke). | Run §5a — if it returns ≤ 2 on the multi.md fixture, the cursor-based scan in `_wrap_anchors_in_paragraph` is broken. Check `git log -- skills/docx/scripts/docx_add_comment.py`. |
| Word reports "couldn't read content" on the produced file. | `[Content_Types].xml` missing the comments Override (regression in `_ensure_content_type`), or comments.xml namespace mismatch. | Run `python -m office.validate /tmp/out.docx`; rerun §3 commands; if `comments.xml` is byte-zero, the script's `_ensure_comments_part` was bypassed — check for an upstream `comments.xml` that is empty. |
| Exit 2, `ParentCommentNotFound` JSON envelope. | `--parent N` references a comment id that doesn't exist in `word/comments.xml`. | List existing ids with `python -c "import zipfile,re;z=zipfile.ZipFile('FILE.docx');print(re.findall(r'<w:comment w:id=\"(\\d+)\"',z.read('word/comments.xml').decode()))"` and use one of those. |
| Exit 2, `ParentRangeNotFound` JSON envelope. | Parent comment exists in `comments.xml` but its `<w:commentRangeStart/End>` markers are missing in `document.xml` — the file is structurally inconsistent. | Run `python -m office.validate FILE.docx --strict`; the validator will report the orphan comment id. The fix is upstream — reproduce or repair the parent file before adding the reply. |
| Reply renders as a sibling top-level comment in Word, not a thread. | `paraIdParent` in `commentsExtended.xml` doesn't match the parent's `w14:paraId` in `comments.xml`. | Inspect both: `python -c "import zipfile;z=zipfile.ZipFile('FILE.docx');print(z.read('word/comments.xml').decode());print(z.read('word/commentsExtended.xml').decode())"` — the hex IDs must agree. Pre-2021 files without `w14:paraId` get an auto-back-fill on first reply; if the upstream lib stripped that, the linkage will be off. |
| Exit 2, `UsageError`: "--unpacked-dir is mutually exclusive with INPUT/OUTPUT". | You passed both `INPUT OUTPUT` positionals and `--unpacked-dir DIR`. | Pick one mode. Library mode never takes positionals; it edits `DIR` in-place. |
| `office.unpack` says fine, but library-mode add-comment exits 1 with `NotADocxTree`. | The directory passed to `--unpacked-dir` is missing `word/document.xml` — likely you pointed at the parent directory of an unpacked tree. | Pass the directory that *directly contains* `[Content_Types].xml` and `word/`. |
| Exit 1, `MalformedOOXML` JSON envelope. | One of `comments.xml`, `commentsExtended.xml`, `commentsIds.xml`, `commentsExtensible.xml` is not well-formed XML — the file is corrupt or was hand-edited badly. | The envelope's `details.detail` carries the lxml error (line/column). Re-unpack from a fresh `.docx` if possible; otherwise repair the offending part by hand. The script never invents the error — it always points at a real syntax issue. |
| Two `--unpacked-dir DIR` processes ran in parallel and ended up with fewer comments than they added. | Library mode is **not reentrant**: there is no file locking around the read-modify-write cycle on `comments.xml` / `commentsExtended.xml` / `document.xml`. The later writer clobbers the earlier writer's changes. | Serialize external concurrency yourself — wrap the call site in `flock`, or fan out by maintaining one tree per process. The single-process zip-mode (`INPUT.docx OUTPUT.docx`) is safe under concurrency since each call gets its own temp tree. |
| Reply-to-reply ends up flat in Word's review pane instead of nested. | Intentional. The script walks `paraIdParent` in `commentsExtended.xml` to the conversation root and points the new reply there — that is what Word writes when a user clicks "Reply" on a reply, and what Word's Reply button expects to read back. Disk shape stays canonical. | None — this is the documented behavior. If you genuinely need a chain (rare), edit `commentsExtended.xml` by hand after running the script. |
| Multi-paragraph comment body collapses to one line in Word. | `--comment` was given without `\n` separators — body is a single paragraph. | Pass `--comment $'line one\nline two'` (bash `$'…'` escapes), or build the comment XML by hand and use library mode. The script splits on `\n` per ECMA-376 §17.13.4.2; `\r\n` is normalized first. |

---

## 7. Reference

- ECMA-376 Part 1 §17.13 — comments part, range markers, reference run.
- ISO/IEC 29500-1 Transitional + MS-DOCX (`w14:paraId`, `w15:commentEx`,
  `w16cid:commentId`, `w16cex:commentExtensible`) — open extensions used by
  Word 2010+/2016+/2018+ to thread replies and persist durable IDs.
- [`SKILL.md`](../SKILL.md) §10 Quick Reference — one-line invocation
  (anchor / reply / library mode).
- [`scripts/tests/test_e2e.sh`](../scripts/tests/test_e2e.sh) lines
  covering `docx-1 add_comment:` (anchor mode) and `docx-1b
  add_comment replies + library:` (reply + library mode) — automated
  regression.
- The cross-5 envelope contract: any failure with `--json-errors` is a
  single line of valid JSON (`{v, error, code, type, details}`) on
  stderr; see [`scripts/_errors.py`](../scripts/_errors.py).
