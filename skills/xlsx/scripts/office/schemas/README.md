# OOXML XSD Schemas

This directory ships only the W3C `xml.xsd` by default. The ECMA-376
and Microsoft schema sets are large and are not bundled by default to
keep the repository small. Fetch them with `./fetch.sh` when you need
full XSD validation.

## Contents

- `w3c/xml.xsd` — W3C XML namespace schema (bundled).
  Source: <https://www.w3.org/2001/xml.xsd>
  License: <https://www.w3.org/copyright/document-license/>
- `ecma-376/` — Office Open XML schemas (WordprocessingML,
  SpreadsheetML, PresentationML, DrawingML, Open Packaging Conventions,
  Markup Compatibility Extensions). Not bundled; run `./fetch.sh`.
  Source: <https://ecma-international.org/publications-and-standards/standards/ecma-376/>
- `microsoft/` — Microsoft namespace extensions (`w14`, `w15`,
  `w16cid`, `w16cex`, `w16du`, `w16sdtdh`, `w16sdtfl`, `w16se`,
  equivalents for spreadsheet and presentation namespaces). Not bundled;
  fetch on demand from Microsoft Learn.
  Source: <https://learn.microsoft.com/en-us/openspecs/office_standards/>

## License and redistribution

- ECMA-376 schemas are © Ecma International / ISO-IEC, redistributable
  under the Ecma open specification policy.
- Microsoft extensions fall under the Microsoft Open Specification
  Promise: <https://learn.microsoft.com/en-us/openspecs/dev_center/ms-devcentlp/51c5a3fd-e73a-4cec-b65c-3e4094d0ea12>
- `xml.xsd` is under the W3C Document License.

Attribution for any bundled schema is recorded in the project-level
`THIRD_PARTY_NOTICES.md`.

## Fetching everything

```bash
bash fetch.sh
```

The script downloads the ECMA-376 5th-edition ZIP from ecma-international.org
and extracts the schemas into `ecma-376/`. Microsoft extensions are
distributed as individual `.xsd` files linked from Microsoft Learn; the
script leaves a note listing them rather than pulling every file (the
URLs shift every Office release).

## Validator behaviour without schemas

`validate.py` runs its structural and consistency checks unconditionally;
XSD binding is skipped for any part whose schema isn't present. Add
`--strict` to turn missing-schema warnings into errors.
