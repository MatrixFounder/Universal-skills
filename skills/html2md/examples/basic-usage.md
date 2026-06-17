# html2md — basic usage examples

> Skeleton examples (bead 022-01). Full worked examples with sample fixtures are
> authored in bead 022-07.

## Clip a live URL into an Obsidian vault folder

```bash
python3 scripts/html2md.py https://example.com/some-article ./MyVault/Clips/
# → ./MyVault/Clips/some-article.md          (whole page)
#   ./MyVault/Clips/some-article.reader.md    (reader-extracted)
#   ./MyVault/Clips/_attachments/<sha1>.png   (downloaded images, deduped)
```

## Convert a downloaded archive offline (no network)

```bash
python3 scripts/html2md.py ./saved-page.webarchive ./out/ --archive-frame main
python3 scripts/html2md.py ./email.mhtml ./out/ --archive-frame all
```

## Use as a universal agent step (Markdown on stdout, no files)

```bash
python3 scripts/html2md.py ./page.html --stdout --no-download-images --no-reader --json-errors
# → whole-page Markdown on stdout; failures as a single-line {"v":1,...} envelope
```

## Force the Chrome engine for a JS/SPA page (opt-in)

```bash
bash scripts/install.sh --with-chrome
python3 scripts/html2md.py https://some-spa.example/app ./out/ --engine chrome
```
