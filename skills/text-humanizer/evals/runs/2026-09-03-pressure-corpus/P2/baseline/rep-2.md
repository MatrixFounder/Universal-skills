## Export service on-call runbook

`POST /v2/exports` renders a report and hands back a job id. Under the hood the worker drives a headless Chrome instance over CDP; the `Page.navigate` call is capped at a hard 30 s timeout, and a job that runs past it comes back as `ETIMEDOUT`. Wide tables need `orientation=landscape` — portrait is the default otherwise.

Auth is a bearer token. Send nothing, or send something expired, and you get a `401` back with `WWW-Authenticate: Bearer realm="exports"` in the header. The gateway caps each token at 20 requests a minute and queues whatever's left over. Retries start at a 200 ms wait, double each time after that, and top out at 15 minutes.

Worker containers attach to `br0`, the bridge interface on the render host. When `br0` is down the workers still come up fine, but every job dies with `EAGAIN` at the socket layer. Check `ip link show br0` before you restart anything.

Anything with a leading underscore in the field name — `_internal`, `_trace_id`, `_shard` — is internal and can change without warning; it was never part of the contract. Both `exportctl get --highlight-syntax` and the plain writer print these fields, colour or not, which is exactly how they end up in customer tickets.