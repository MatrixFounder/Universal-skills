## Export service on-call runbook

`POST /v2/exports` renders a report and hands back a job id. The worker runs a headless Chrome instance over CDP; the `Page.navigate` call carries a hard 30 s timeout, and a job that hits it ends in `ETIMEDOUT`. For wide tables, pass `orientation=landscape`. Portrait is the default otherwise.

The export tier sits between the reporting stack and the rest of the observability system.

Auth runs on a bearer token. Miss it, or let it expire, and the call comes back `401` with `WWW-Authenticate: Bearer realm="exports"` in the header. The gateway caps each token at 20 requests a minute and queues anything over that. Retries start at 200 ms and double each time, capping out at 15 minutes.

Worker containers attach to `br0`, the render host's bridge interface. Workers start fine even when `br0` is down; they just fail every job with `EAGAIN` at the socket layer. Check `ip link show br0` before you restart anything.

Field names starting with an underscore, like `_internal`, `_trace_id`, `_shard`, are internal. They're not part of the contract and can change without notice. `exportctl get --highlight-syntax` prints them in colour, and the plain writer does too, which is exactly how they end up in customer tickets.