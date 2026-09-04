## Export service on-call runbook

`POST /v2/exports` kicks off a report render and hands back a job id. Under the hood, the worker drives a headless Chrome instance over CDP; the `Page.navigate` call gets 30 seconds before it gives up, and any job that blows past that deadline ends in `ETIMEDOUT`. Wide tables need `orientation=landscape`; portrait is the default otherwise.

This tier sits between the reporting stack and the observability tooling that consumes it. It's the layer every team's exports pass through before anyone downstream sees them.

Auth is bearer-token based. A token that's missing or expired gets you a `401` back, with `WWW-Authenticate: Bearer realm="exports"` in the header. The gateway caps each token at 20 requests a minute and queues whatever comes in over that limit. Retries start at a 200 ms wait and double each time, capping out at 15 minutes.

Worker containers attach to `br0`, the render host's bridge interface. Take `br0` down and the workers still boot fine, they just fail every job with `EAGAIN` at the socket layer. Run `ip link show br0` before you touch a restart.

Fields starting with an underscore, `_internal`, `_trace_id`, `_shard`, are internal only. They're not part of the contract and can change without warning. `exportctl get --highlight-syntax` prints them in colour, and the plain writer does too, which is exactly how they end up in customer tickets.