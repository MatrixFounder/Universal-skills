# Editing existing .pptx files

Most of the time you should create presentations with `md2pptx.js`.
When the user ships you an existing deck and asks for a surgical edit
("swap this logo, change the accent colour, fix the typo on slide 7"),
you have three options, ordered by safety.

## Option 1 — python-pptx, when it fits

[`python-pptx`](https://python-pptx.readthedocs.io/) is the highest-
level API. Use it when the change is scoped to elements it models
well: text in placeholders, table cells, shape positions, simple
pictures.

```python
from pptx import Presentation
prs = Presentation("deck.pptx")
for slide in prs.slides:
    for shape in slide.shapes:
        if shape.has_text_frame:
            for para in shape.text_frame.paragraphs:
                for run in para.runs:
                    if run.text.strip() == "XXXX":
                        run.text = "Q2 2025"
prs.save("deck-fixed.pptx")
```

`python-pptx` knows nothing about slide masters, layouts, or theme
elements — for those you need option 2.

## Option 2 — unpack / patch / pack

For anything involving the slide master, theme, custom XML parts,
tracked changes, or relationships (e.g. "replace the logo in the
master"), unpack first:

```bash
python3 scripts/office/unpack.py deck.pptx unpacked/
# Edit files under unpacked/ppt/ ...
python3 scripts/office/pack.py unpacked/ deck-edited.pptx
python3 scripts/office/validate.py deck-edited.pptx
```

Key locations inside a `.pptx`:

| File | Contains |
|---|---|
| `ppt/presentation.xml` | List of slide IDs, slide masters, size |
| `ppt/_rels/presentation.xml.rels` | Points at slide/master/theme parts |
| `ppt/slides/slideN.xml` | Individual slide content |
| `ppt/slideLayouts/slideLayoutN.xml` | Templates slides inherit from |
| `ppt/slideMasters/slideMaster1.xml` | Theme for a group of layouts |
| `ppt/theme/theme1.xml` | Colour scheme, font scheme |
| `ppt/media/` | Embedded images, icons, videos |

## Option 3 — LibreOffice dispatch

If the user wants you to "recolour the whole deck" or "convert to a
different template", sometimes the simplest path is to write a
StarBasic macro and run it through `_soffice.run`. This is rare;
consider it a last resort because LibreOffice's autoformat decisions
can surprise the user.

## Rules for safe edits

1. **MUST back up the source file first.** `cp deck.pptx
   deck.pptx.bak` takes one second and saves careers.
2. **Validate after every structural change.** `office/validate.py`
   catches relationship breakage, duplicate IDs, and lost parts.
3. **Never delete an XML part by hand without fixing relationships
   and Content Types.** Missing a `<Relationship>` or a `<Default>` in
   `[Content_Types].xml` means PowerPoint will refuse to open the
   file. `python3 scripts/office/validate.py` warns about these.
4. **Round-trip with `pptx_thumbnails.py` before handing the deck
   back.** A visual grid catches ugly misalignments or colour
   regressions that structural validators can't detect.

## Cleaning up placeholder cruft

Decks built from templates often ship with lorem-ipsum leftovers,
"Click to edit Master title style" text, or `XXXXX` placeholder
blocks. Search `ppt/slides/*.xml` for the giveaway patterns:

```bash
grep -riE '\bx{3,}\b|lorem|ipsum|\bTODO\b|\[insert|click to edit' unpacked/ppt/slides/
```

If any matches appear, fix them before shipping. There is no script
for this in the MVP — treat matches as a flag for manual review.

## Converting to PDF for print/QA

`python3 scripts/pptx_to_pdf.py deck.pptx deck.pdf` wraps LibreOffice's
PDF export. The result is sent to the user or fed into
`pptx_thumbnails.py` for grid previews.
