Waiting on a query is dead time. Vantage 3.2 goes after that directly.

In our internal benchmark, query latency dropped from 840 ms to 210 ms. That's not a rounding error. It's roughly four times faster on the same workload teams run every day.

The export pipeline now handles 2.4 million rows without paging, so a full dataset stops meaning ten separate exports stitched together by hand. SSO now covers Okta and Azure AD too, one less workaround for IT to maintain.

None of it required reinventing Vantage. We just cut the parts that made people wait.