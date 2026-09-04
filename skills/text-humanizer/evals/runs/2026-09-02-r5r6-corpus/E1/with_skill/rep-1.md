If Vantage felt slow before, 3.2 is the fix.

Query latency dropped from 840 ms to 210 ms in our internal benchmark. That's the difference between waiting on a query and not waiting on one. The export pipeline got the same treatment. It now handles 2.4 million rows without paging.

SSO now supports Okta and Azure AD too.

None of this is flashy. It's just faster. That's the point.