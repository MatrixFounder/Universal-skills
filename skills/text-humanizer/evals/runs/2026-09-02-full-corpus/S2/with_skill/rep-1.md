We ripped the job queue out of Redis last quarter and rebuilt it on Postgres.

Reason: Redis was losing jobs on failover — about 40 a week, out of 2.1 million. Not a huge share. But losing jobs at all is the kind of bug that erodes trust in a queue.

Postgres with SKIP LOCKED took that number to zero. Eleven weeks, no losses. The tradeoff: p99 enqueue latency went from 1.2 ms to 6.8 ms.

I'd make that trade again. A few extra milliseconds beat a job that just disappears.