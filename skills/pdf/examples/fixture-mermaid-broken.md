# Broken mermaid fixture

The mermaid block below contains intentionally invalid syntax. This
fixture exercises two paths:

1. `--strict-mermaid` → mmdc fails → md2pdf exits non-zero with the
   stderr captured.
2. Default (no `--strict-mermaid`) → mmdc fails → md2pdf prints a
   warning to stderr, leaves the block as a code fence, and still
   produces a valid PDF.

```mermaid
graph LR
    A[start] -->|broken arrow ((((|
    %%this is not balanced
    B{wat
```
