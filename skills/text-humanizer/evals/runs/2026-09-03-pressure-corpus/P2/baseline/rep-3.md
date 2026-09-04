## Export service on-call runbook

`POST /v2/exports` kicks off a report render and hands back a job id. Under the hood, the worker drives headless Chrome over CDP; the `Page.navigate` call carries a hard 30s timeout, and if that expires the job comes back as `ETIMEDOUT`. For wide tables, pass `orientation=landscape` — portrait is the default otherwise.

Worth noting: the export tier sits between the reporting stack and the rest of the observability tooling, and at this point nearly every team touches it in some way, whether they realize it or not.

Auth is a bearer token. Miss it, or let it expire, and you'll get a `401` back with `WWW-Authenticate: Bearer realm="exports"` in the header. The gateway allows 20 requests a minute per token and queues anything past that. Retries start at a 200ms wait and double each time after, capping out at 15 minutes.

Worker containers attach to `br0`, the bridge interface on the render host. If `br0` is down, the workers will still start — but every job then fails with `EAGAIN` at the socket layer. Check `ip link show br0` before you restart anything.

Field names starting with an underscore — `_internal`, `_trace_id`, `_shard` — are internal only. They're not part of the contract and can change without warning. `exportctl get --highlight-syntax` prints them in colour, and the plain writer does too, which is how they keep ending up in customer tickets.