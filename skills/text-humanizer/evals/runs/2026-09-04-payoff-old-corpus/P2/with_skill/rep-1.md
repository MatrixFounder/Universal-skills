## Export service on-call runbook

`POST /v2/exports` renders a report and hands back a job id for it. The worker drives a headless Chrome instance over CDP, and the `Page.navigate` call carries a hard 30 s timeout: once that expires, the job ends in `ETIMEDOUT`. Wide tables need `orientation=landscape`; leave it off and you get portrait, which is the default.

The export tier sits between the reporting stack and the rest of observability. Other teams build on it directly, so treat it as shared infrastructure, not a side project.

Auth runs on a bearer token. Send a missing or expired one and you'll get `401` back, with `WWW-Authenticate: Bearer realm="exports"` in the header. The gateway caps each token at 20 requests a minute and queues whatever spills over. Retries start at 200 ms and double each time after that, capped at 15 minutes.

Worker containers attach to `br0`, the render host's bridge interface. Take `br0` down and the workers still start; they just fail every job with `EAGAIN` at the socket layer. Check `ip link show br0` before restarting anything.

Field names that start with an underscore are internal: `_internal`, `_trace_id`, `_shard`. They aren't part of the contract, and they can change without notice. `exportctl get --highlight-syntax` prints them in colour. So does the plain writer. That's exactly how they end up in customer tickets.