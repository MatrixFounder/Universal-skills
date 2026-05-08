# Third-Party Notices

This repository (Universal-skills) is licensed under the Apache License,
Version 2.0. See [LICENSE](LICENSE) for the full license text.

Some files bundled under `skills/*/scripts/office/schemas/` and some
dependencies used at runtime are authored by third parties and remain
under their respective licenses. No source code from Anthropic's
proprietary `docx`, `pptx`, `xlsx`, or `pdf` skills has been copied into
this repository; all implementations are original work written against
public specifications.

## XML Schema Definitions

OOXML schemas are distributed unchanged from their public sources.

- **ECMA-376 / ISO/IEC 29500** (Office Open XML — WordprocessingML,
  SpreadsheetML, PresentationML, DrawingML, Open Packaging Conventions,
  Markup Compatibility Extensions)
  Publisher: Ecma International, © Ecma International and ISO/IEC.
  Source: https://ecma-international.org/publications-and-standards/standards/ecma-376/
  Ecma International publishes its standards free of charge and permits
  their copying for implementation purposes. See the Ecma Code of Conduct
  in Patent Matters and Ecma Copyright Policy.

- **Microsoft Open Specification Promise** — namespace extensions used
  by modern Microsoft Office (`w14`, `w15`, `w16cid`, `w16cex`, `w16du`,
  `w16sdtdh`, `w16sdtfl`, `w16se`, and related).
  Source: https://learn.microsoft.com/en-us/openspecs/office_standards/
  OSP text: https://learn.microsoft.com/en-us/openspecs/dev_center/ms-devcentlp/51c5a3fd-e73a-4cec-b65c-3e4094d0ea12

- **W3C Document License** — `xml.xsd` (XML namespace schema).
  Source: https://www.w3.org/2001/xml.xsd
  License: https://www.w3.org/copyright/document-license/

## Python Libraries (runtime dependencies)

Installed via `pip install -r scripts/requirements.txt` in each skill.
None are bundled in this repository.

| Package | License | Used by |
|---|---|---|
| `lxml` | BSD-style | docx, xlsx, pptx (XML parsing, XSD validation) |
| `defusedxml` | PSF License | docx, xlsx, pptx (safe XML parsing) |
| `python-docx` | MIT | docx (template fill, document manipulation) |
| `openpyxl` | MIT-style | xlsx (workbook creation, editing, validation) |
| `pandas` | BSD-3-Clause | xlsx (tabular data loading) |
| `regex` | Apache-2.0 | xlsx (rule-eval per-cell `timeout=` parameter — stdlib `re` lacks this; xlsx-7 / `xlsx_check_rules.py`) |
| `python-dateutil` | Apache-2.0 / BSD-3-Clause dual-licensed | xlsx (`--treat-text-as-date` opt-in date parser; xlsx-7) |
| `ruamel.yaml` | MIT | xlsx (YAML 1.2 loader with event-stream alias rejection — PyYAML's `safe_load` does NOT block alias expansion; xlsx-7) |
| `python-pptx` | MIT | pptx (presentation manipulation) |
| `Pillow` | HPND | pptx (image composition for thumbnails) |
| `pypdf` | BSD-3-Clause | pdf (merge, split, metadata) |
| `pdfplumber` | MIT | pdf (layout-aware text/table extraction) |
| `weasyprint` | BSD-3-Clause | pdf (Markdown/HTML → PDF) |
| `markdown2` | MIT | pdf (Markdown → HTML preprocessing) |

## JavaScript Libraries (runtime dependencies)

Installed via `npm install` in each skill's `scripts/` directory. None
are bundled in this repository.

| Package | License | Used by |
|---|---|---|
| `docx` (docx-js) | MIT | docx/md2docx.js |
| `marked` | MIT | docx/md2docx.js, pptx/md2pptx.js |
| `mammoth` | Apache-2.0 | docx/docx2md.js |
| `turndown` | MIT | docx/docx2md.js |
| `turndown-plugin-gfm` | MIT | docx/docx2md.js |
| `image-size` | MIT | docx/md2docx.js |
| `pptxgenjs` | MIT | pptx/md2pptx.js |
| `@mermaid-js/mermaid-cli` | MIT | docx/md2docx.js (optional mermaid rendering) |

## External Command-Line Tools (not bundled, invoked via PATH)

| Tool | License | Used by |
|---|---|---|
| LibreOffice (`soffice`) | MPL-2.0 | docx (accept changes), xlsx (recalc), pptx (convert to PDF, thumbnails) |
| Poppler (`pdftoppm`) | GPL-2.0-or-later | pptx (thumbnails) |
| Pandoc | GPL-2.0-or-later | optional alternative paths in docx/pdf |

GPL-licensed tools are invoked as unmodified standalone binaries via
`subprocess`; this repository does not link against or redistribute them.

## Attribution

When redistributing this repository or its skills, retain this file
alongside `LICENSE` and do not remove the attribution blocks for
ECMA-376, the Microsoft Open Specification Promise, or the W3C Document
License that ship in `skills/*/scripts/office/schemas/`.
