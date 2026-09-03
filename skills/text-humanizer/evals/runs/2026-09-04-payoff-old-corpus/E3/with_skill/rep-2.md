Tuesday cost me three hours chasing a bug. The culprit: a stale DNS cache on one of the build agents. The fix, when I finally found it, was one line in the Dockerfile.

Here's what actually gets me. That agent had been flaking on and off for a week, and nobody filed anything. Why would they? "It passes on retry" is the kind of line that closes an investigation before it opens one.

So the build now fails loudly whenever a lookup crawls past 500 ms. Two people have already complained.

Good.