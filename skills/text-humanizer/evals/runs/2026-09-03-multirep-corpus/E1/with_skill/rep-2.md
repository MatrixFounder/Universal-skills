Slow queries, exports that needed paging to push through, and no native login for teams on Okta or Azure AD. That's the list Vantage 3.2 goes after.

Query latency dropped from 840 ms to 210 ms in our internal benchmark. The new export pipeline handles 2.4 million rows without paging. SSO now supports Okta and Azure AD.

That's 3.2. Nothing flashy. Just the parts of the workflow that used to slow people down, fixed.