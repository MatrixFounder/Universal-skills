# Large mindmap fixture

5 branches × 8 leaves. Stress-tests mmdc's mindmap layout (used to
overflow page boundaries; the `.mermaid-diagram { max-height: 7in }`
rule in `md2pdf.py` is what keeps these on a single page).

```mermaid
mindmap
  root((Roadmap 2026))
    Product
      Onboarding redesign
      Mobile parity
      Self-serve plan
      Permissions v2
      Search rewrite
      Notifications
      Audit log UI
      A/B framework
    Engineering
      Telemetry pipeline
      Cold-storage tier
      Schema registry
      Async job runner
      Build cache
      DX week
      Type-checker bump
      Observability spans
    Growth
      SEO programmatic
      Lifecycle emails
      Referral loop
      Pricing test
      Partner pages
      Webinar series
      Ad creative
      Localisation pilot
    Trust
      SOC2 type II
      Pen-test followups
      Threat model refresh
      Customer DPAs
      Subprocessor list
      Data retention
      Encryption-at-rest
      SSO hardening
    Hiring
      Sr. backend
      Design lead
      ML infra
      EU support
      DevRel
      Ops eng
      Recruiter coord
      Internships
```
