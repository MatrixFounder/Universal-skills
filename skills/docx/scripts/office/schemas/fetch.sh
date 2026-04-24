#!/usr/bin/env bash
# Bootstrap ECMA-376 XSD schemas for `office/validate.py --strict`.
#
# Downloads the public 5th-edition ZIP from ecma-international.org and
# extracts the XSD parts that ship inside OfficeOpenXML-XMLSchema-*.
#
# Safe to re-run: skips the download if the archive already exists.

set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ECMA_DIR="$HERE/ecma-376"
TMP_DIR="$HERE/.tmp"
ARCHIVE_URL="https://ecma-international.org/wp-content/uploads/ECMA-376-5th-edition-December-2021.zip"
ARCHIVE_NAME="ecma-376-5th.zip"

mkdir -p "$ECMA_DIR" "$TMP_DIR"

if [[ ! -f "$TMP_DIR/$ARCHIVE_NAME" ]]; then
  echo "Downloading $ARCHIVE_URL ..." >&2
  curl -fL --retry 2 -o "$TMP_DIR/$ARCHIVE_NAME" "$ARCHIVE_URL"
fi

echo "Extracting XSD parts into $ECMA_DIR ..." >&2
# ECMA-376 5th edition packs the XSDs inside a nested ZIP — handle both
# layouts by extracting to a staging dir and rsyncing every .xsd.
STAGE="$TMP_DIR/extract"
rm -rf "$STAGE"
mkdir -p "$STAGE"
unzip -qo "$TMP_DIR/$ARCHIVE_NAME" -d "$STAGE"

# Some ECMA packages ship a second zip with just the schemas.
while IFS= read -r nested; do
  unzip -qo "$nested" -d "$STAGE"
done < <(find "$STAGE" -maxdepth 3 -name "*.zip" -type f)

find "$STAGE" -name "*.xsd" -type f -exec cp -f {} "$ECMA_DIR/" \;

echo "Done. $(find "$ECMA_DIR" -name '*.xsd' | wc -l) XSD files in $ECMA_DIR" >&2
echo
echo "For Microsoft namespace extensions (w14/w15/w16*, xlsx/pptx equivalents):"
echo "  https://learn.microsoft.com/en-us/openspecs/office_standards/"
echo "  Download the individual .xsd files and place them under: $HERE/microsoft/"
