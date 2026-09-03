Query latency used to sit at 840 ms. On Vantage 3.2, it's down to 210 ms in our internal benchmark. Same workload, a quarter of the wait.

The export pipeline stopped choking on big jobs. It pushes through 2.4 million rows without paging.

SSO now covers both Okta and Azure AD. If either was the reason your rollout stalled, that reason is gone.