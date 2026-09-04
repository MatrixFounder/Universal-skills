## Retry behaviour

Retries follow a dynamic backoff schedule: the first one fires after 200 ms, and each attempt after that doubles the wait, up to a 30 s ceiling.

One exception — setting `robust_mode=true` removes that ceiling. With robust mode on, the client just keeps retrying until the deadline passes.

Buffers need to be aligned to a 64-byte boundary; if one isn't, you'll get `EINVAL`.

As for scheduling, it's dynamic too: new workers get added once the queue depth passes 10000 messages.