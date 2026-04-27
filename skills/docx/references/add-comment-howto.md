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

The script touches **four** OOXML parts. Inspect each to confirm:

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

---

## 7. Reference

- ECMA-376 Part 1 §17.13 — comments part, range markers, reference run.
- [`SKILL.md`](../SKILL.md) §10 Quick Reference — one-line invocation.
- [`scripts/tests/test_e2e.sh`](../scripts/tests/test_e2e.sh) lines covering `docx-1 add_comment:` — automated regression.
- The cross-5 envelope contract: any failure with `--json-errors` is a
  single line of valid JSON (`{v, error, code, type, details}`) on
  stderr; see [`scripts/_errors.py`](../scripts/_errors.py).
