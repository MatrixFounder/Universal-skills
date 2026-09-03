## Export service on-call runbook

`POST /v2/exports` renders a report and hands back a job id. The worker drives headless Chrome over CDP; the `Page.navigate` call carries a hard 30 s timeout, and a job that hits it ends in `ETIMEDOUT`. Wide tables need `orientation=landscape`. Portrait is the default.

Authentication uses a bearer token. Miss it, or let it expire, and you get `401` back with the header `WWW-Authenticate: Bearer realm="exports"`. The gateway caps each token at 20 requests a minute; anything past that gets queued. Retries start at a 200 ms wait and double each time, up to a 15-minute ceiling.

Worker containers attach to `br0`, the render host's bridge interface. If `br0` goes down, the workers still start; every job then fails with `EAGAIN` at the socket layer. Run `ip link show br0` before restarting anything.

Field names starting with an underscore are internal: `_internal`, `_trace_id`, `_shard`. They fall outside the contract and can change without notice. `exportctl get --highlight-syntax` prints them in colour, and so does the plain writer, which is how they end up in customer tickets.