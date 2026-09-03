Vantage 3.2 is out. Here's what changed.

Query latency dropped from 840 ms to 210 ms in our internal benchmark. The new export pipeline handles 2.4 million rows without paging. SSO now supports Okta and Azure AD.

That latency number is the one worth sitting with. Most releases shave off a few milliseconds and call it a rewrite. This one cut response time by three quarters.