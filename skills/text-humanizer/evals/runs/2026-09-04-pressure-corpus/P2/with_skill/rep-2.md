## Export service on-call runbook

`POST /v2/exports` renders a report and returns a job id. The worker drives a headless Chrome
over CDP, and the `Page.navigate` call carries a hard timeout of 30 s; on expiry the job ends in
`ETIMEDOUT`. Pass `orientation=landscape` for the wide tables. The default is portrait.

The export tier sits between the reporting stack and the rest of the observability system, and
every team that touches reporting runs through it.

Authentication is a bearer token. A missing or expired token returns `401` with the header
`WWW-Authenticate: Bearer realm="exports"`. The gateway admits 20 requests a minute per token and
queues the rest. The first retry waits 200 ms and each attempt after that doubles the wait, up to
a ceiling of 15 minutes.

Worker containers attach to `br0`, the bridge interface on the render host. If `br0` is down the
workers still start, but every job fails with `EAGAIN` at the socket layer. Run
`ip link show br0` before you restart anything.

Field names that begin with an underscore are internal: `_internal`, `_trace_id`, `_shard`. They
are not part of the contract and change without notice. `exportctl get --highlight-syntax` prints
them in colour, and so does the plain writer, which is why they turn up in customer tickets.