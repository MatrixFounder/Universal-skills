Certainly! Let's delve into this.

We migrated our job queue from Redis to Postgres last quarter — and it was not just a migration,
it was a fundamental rethinking of our robust, seamless, and intuitive infrastructure.

The reason was simple. Redis lost jobs on failover: about 40 per week out of 2.1 million.
Postgres with SKIP LOCKED gave us 0 in eleven weeks, at the cost of p99 enqueue latency going
from 1.2 ms to 6.8 ms.

Moreover, this underscores the importance of durability, highlighting the trade-offs inherent in
queue design.
