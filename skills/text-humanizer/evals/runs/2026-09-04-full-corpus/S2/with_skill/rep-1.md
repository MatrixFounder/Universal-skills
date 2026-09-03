We moved our job queue off Redis and onto Postgres last quarter. It wasn't a small swap.

Simple reason: Redis was losing jobs on failover — about 40 a week out of 2.1 million. Switch to Postgres with SKIP LOCKED and that number goes to zero, eleven weeks running. It cost us: p99 enqueue latency climbed from 1.2 ms to 6.8 ms.

Worth it. A few extra milliseconds beats jobs disappearing without a trace.