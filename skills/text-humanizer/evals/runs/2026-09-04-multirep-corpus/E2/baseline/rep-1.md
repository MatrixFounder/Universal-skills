## Retry behaviour

Backoff is dynamic on the client side: the first retry goes out 200 ms after the initial failure, and each attempt after that doubles the wait, capping out at 30 s.

One exception — setting `robust_mode=true` removes that cap entirely. With robust mode on, the client just keeps retrying until the deadline is hit.

Buffers need to be aligned to a 64-byte boundary, or you'll get an `EINVAL`.

Worker scaling is also dynamic: new workers get spun up once queue depth passes 10000 messages.