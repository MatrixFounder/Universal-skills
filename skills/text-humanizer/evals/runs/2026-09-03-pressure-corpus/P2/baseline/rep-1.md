## Export service on-call runbook

`POST /v2/exports` renders a report and hands back a job id. Under the hood, the worker drives a headless Chrome instance over CDP. The `Page.navigate` call has a hard 30 s timeout, and anything that hits it ends up failing with `ETIMEDOUT`. For wide tables, pass `orientation=landscape` — portrait is the default otherwise.

The export tier sits between the reporting stack and the rest of observability, translating job requests into rendered output for whichever team needs them.

Auth is a bearer token. Send one that's missing or expired and you'll get back a `401` with `WWW-Authenticate: Bearer realm="exports"`. The gateway caps each token at 20 requests a minute and queues whatever comes in over that. Retries start at a 200 ms wait and double each time after, up to a ceiling of 15 minutes.

Worker containers attach to `br0`, the bridge interface on the render host. When `br0` is down, the workers still come up fine, but every job then fails at the socket layer with `EAGAIN`. Check `ip link show br0` before you touch anything else.

Fields prefixed with an underscore — `_internal`, `_trace_id`, `_shard` — are internal and not part of the contract, so they can change without notice. Both `exportctl get --highlight-syntax` and the plain writer print them in colour, which is exactly how they keep showing up in customer tickets.