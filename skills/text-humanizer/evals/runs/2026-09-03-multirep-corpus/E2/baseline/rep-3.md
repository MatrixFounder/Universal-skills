## Retry behaviour

Retries follow a dynamic backoff schedule: the first one fires 200 ms after failure, and each attempt after that doubles the wait, up to a 30-second ceiling.

Setting `robust_mode=true` removes that ceiling — with it on, the client keeps retrying until the deadline passes.

Buffers need to be aligned to a 64-byte boundary; a misaligned buffer raises `EINVAL`.

The scheduler also adjusts worker count dynamically, adding workers once queue depth passes 10000 messages.