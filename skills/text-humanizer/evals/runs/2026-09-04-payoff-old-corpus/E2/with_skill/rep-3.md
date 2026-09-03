## Retry behaviour

Retries follow an exponential backoff: the first attempt fires at 200 ms, then each subsequent try doubles the wait, up to a 30 s cap.

Set `robust_mode=true` to remove that cap. With robust mode on, the client keeps retrying until the deadline passes.

Buffers need 64-byte alignment. A misaligned buffer raises `EINVAL`.

The scheduler adds workers once queue depth passes 10000 messages.