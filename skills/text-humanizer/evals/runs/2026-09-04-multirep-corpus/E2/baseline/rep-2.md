## Retry behaviour

Retries follow a dynamic backoff schedule: the first one fires at 200 ms, and each attempt after that doubles the wait, capping out at 30 s.

One exception — setting `robust_mode=true` removes that cap. With robust mode on, the client just keeps retrying until the deadline passes.

Buffers need to sit on a 64-byte boundary; anything misaligned throws `EINVAL`.

Worker count adjusts dynamically too — new workers get added once queue depth passes 10000 messages.