# Sheet-naming edge fixture

This fixture exercises the F7 sanitisation algorithm.

## Q1: [Budget]

A heading with forbidden chars `:`, `[`, `]`. Sanitised → `Q1_ _Budget_`.

| Item | Cost |
|------|------|
| A    | 1    |
| B    | 2    |

## Results

First `Results` heading.

| Metric | Value |
|--------|-------|
| Hits   | 100   |
| Misses | 5     |

## results

Second `Results` heading (case-insensitive dedup → `results-2` or `Results-2`).

| Metric | Value |
|--------|-------|
| Hits   | 50    |
| Misses | 7     |

## History

Reserved name — must be suffixed `History_`.

| Year | Event       |
|------|-------------|
| 2024 | Founded     |
| 2025 | Series A    |
