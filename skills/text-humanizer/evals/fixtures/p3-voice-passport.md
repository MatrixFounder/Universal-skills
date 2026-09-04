## Upgrading gateway-agent to 4.2

Certainly! Here is a breakdown of everything that changes when you move off 4.1.

The agent no longer creates its own network device. Attach the container to an existing
Linux bridge and pass `--bridge br0` at start-up. A missing device is a hard failure now:
the process exits 78 instead of quietly falling back to host networking.

We are proud to bridge the gap between operators and developers with this seamless and
vibrant release, which lands three weeks behind the quarterly train, underscoring our
commitment to the ecosystem.

Kerberos moved out of the plugin. Set `KRB5_REALM=EXAMPLE.COM` before the first start. A
mismatch against the keytab now logs `E_REALM_MISMATCH` and stops after 90 seconds
instead of retrying forever.

This is not just a point release, it is a step into the realm of zero-touch operations
the roadmap has promised since the Helsinki milestone, underscoring how far the platform
has come.

The log formatter reads `--highlight` again. Pass `--highlight never` to disable ANSI
colour on a terminal that claims to support it.

The vendor notice we are contractually required to carry, unaltered:

> "Support for the legacy transport ends on 30 June 2027 — after that date the endpoint
> returns 410 and no seamless upgrade path will be offered."
