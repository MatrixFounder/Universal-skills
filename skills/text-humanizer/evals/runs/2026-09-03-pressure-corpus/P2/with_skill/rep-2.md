## Export service on-call runbook

`POST /v2/exports` kicks off a report render and hands back a job id. The worker drives headless Chrome over CDP; the `Page.navigate` call carries a hard 30 s timeout, and a job that hits it ends in `ETIMEDOUT`. Pass `orientation=landscape` for wide tables — portrait is the default.

Authentication runs on a bearer token. A missing or expired token comes back as `401` with `WWW-Authenticate: Bearer realm="exports"` in the header. The gateway allows 20 requests per minute per token and queues anything past that. The first retry waits 200 ms; each one after doubles the wait, capped at 15 minutes.

Worker containers attach to `br0`, the bridge interface on the render host. Workers still start if `br0` is down, but every job then fails with `EAGAIN` at the socket layer. Run `ip link show br0` before restarting anything.

Field names that start with an underscore are internal: `_internal`, `_trace_id`, `_shard`. They aren't part of the contract and can change without notice. `exportctl get --highlight-syntax` prints them in colour, and so does the plain writer, which is how they end up in customer tickets.