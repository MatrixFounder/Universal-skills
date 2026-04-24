---
title: "Quarterly Report"
author: "Operations Team"
---

# Quarterly report — Q1

This fixture exercises the main features of `md2docx.js` so you can
sanity-check the skill's round-trip behaviour end-to-end:

- headings at multiple levels,
- bulleted and numbered lists,
- a small GFM table,
- a code block,
- a blockquote,
- inline **bold** and *italic* text,
- a smart quote "just like this" and an en-dash — for round-trip testing.

## Key metrics

| Metric          | Q4 2024  | Q1 2025  | Δ        |
|-----------------|---------:|---------:|---------:|
| Revenue, USD    |  840,000 |  915,000 |  +8.9%   |
| New customers   |      120 |      137 | +14%     |
| Churn rate      |     3.2% |     2.8% | −0.4 pp  |

## Highlights

1. Shipped the new onboarding flow on schedule.
2. Signed two enterprise accounts in EU region.
3. Reduced infra cost per request by 11% following the cache rewrite.

## Risks

> One provider's SLA breach cost us four hours of uptime in March; we
> are renegotiating the contract and have a fallback ready.

## Code sample

```python
def growth(before: float, after: float) -> float:
    return (after - before) / before
```

## Template placeholders (only relevant for `docx_fill_template.py`)

- Customer name: `{{customer.name}}`
- Total due: `{{invoice.total}}`
- Due date: `{{invoice.due_date}}`

These placeholders render literally when produced by `md2docx.js`; pair
this fixture with `docx_fill_template.py` and a matching JSON payload
to verify the filler works on a non-empty document.
