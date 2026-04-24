# Quarterly Review

## Operations Team, April 2026

---

# Q1 summary

- Revenue grew 8.9% QoQ, with EMEA leading.
- New-customer acquisition reached an all-time high of 137.
- Churn continued its downward trend (2.8%).

---

# Key metrics

| Metric | Q4 2024 | Q1 2025 | Δ |
|---|---:|---:|---:|
| Revenue (USD) | 840,000 | 915,000 | +8.9% |
| New customers | 120 | 137 | +14% |
| Churn rate | 3.2% | 2.8% | −0.4 pp |

---

# Risks

> A provider SLA breach cost four hours of uptime in March; we are
> renegotiating the contract and have a fallback in place.

- Supplier concentration (top 3 > 60% of COGS)
- Planned EU regulation on data export — impact assessment pending
- Hiring shortfall in EMEA sales (2 of 5 reqs open)

---

# Code change highlights

```python
def growth(before: float, after: float) -> float:
    return (after - before) / before
```

- Cache rewrite: 11% lower infra cost per request
- Onboarding flow A/B test: +18% activation
- Migration to new queue library completed ahead of schedule

---

# Next quarter

- Enter APAC with localised offerings
- Close two enterprise pilots currently in POC
- Lift self-service limits for tier-2 accounts
