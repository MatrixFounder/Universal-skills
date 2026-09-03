## Retry behaviour

The client uses a dynamic backoff schedule. The first retry fires after 200 ms; each
subsequent attempt doubles the interval up to a ceiling of 30 s.

Note that `robust_mode=true` disables the ceiling. While robust mode is on, the
client retries until the deadline passes.

Buffers must align to a 64-byte boundary. A misaligned buffer raises `EINVAL`.

Workers are added once the queue depth exceeds 10000 messages.