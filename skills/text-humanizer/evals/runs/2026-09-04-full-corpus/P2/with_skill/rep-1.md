## Export service on-call runbook

`POST /v2/exports` renders a report and hands back a job id. The worker drives a headless Chrome instance over CDP, and `Page.navigate` runs under a hard 30 s timeout; past that, the job ends in `ETIMEDOUT`. Pass `orientation=landscape` for wide tables; portrait is the default.

The export tier sits between the reporting stack and the rest of the observability system.

Authentication runs on a bearer token; a missing or expired one comes back as `401` with the header `WWW-Authenticate: Bearer realm="exports"`. The gateway caps each token at 20 requests a minute and queues whatever comes in over that. Retries start at 200 ms and double each time after, up to a ceiling of 15 minutes.

Worker containers attach to `br0`, the bridge interface on the render host. When `br0` is down, the workers still boot, but every job then fails at the socket layer with `EAGAIN`. Check `ip link show br0` before restarting anything.

Field names that begin with an underscore are internal: `_internal`, `_trace_id`, `_shard`. They are not part of the contract and change without notice. `exportctl get --highlight-syntax` prints them in colour — so does the plain writer, which is how they end up in customer tickets.