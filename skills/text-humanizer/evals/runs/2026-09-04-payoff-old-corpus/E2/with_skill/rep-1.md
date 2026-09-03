## Retry behaviour

The client uses an exponential backoff schedule. The first retry fires after 200 ms; each subsequent attempt doubles the interval up to a ceiling of 30 s.

Setting `robust_mode=true` disables the ceiling. While it's active, the client keeps retrying until the deadline passes.

Buffers must align to a 64-byte boundary. A misaligned buffer raises `EINVAL`.

The scheduler scales: workers are added when the queue depth exceeds 10000 messages.