## Retry behaviour

The client backs off retries in a doubling pattern: the first retry fires at 200 ms, and each attempt after that doubles the interval, up to a ceiling of 30 s.

Setting `robust_mode=true` disables the ceiling: while robust mode is on, the client retries until the deadline passes.

Buffers must align to a 64-byte boundary. A misaligned buffer raises `EINVAL`.

Workers get added once queue depth exceeds 10000 messages.