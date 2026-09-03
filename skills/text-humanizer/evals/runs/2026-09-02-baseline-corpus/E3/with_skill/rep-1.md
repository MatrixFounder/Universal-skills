I spent Tuesday chasing a bug that turned out to be a stale DNS cache on one of the build agents. Three hours. The fix was one line in the Dockerfile.

Here's what actually gets me: that agent had been failing on and off for a week, and nobody filed anything. "It passes on retry" is the kind of sentence that kills an investigation before it starts, not one that starts it.

So now the build fails loud the moment a lookup takes longer than 500 ms. Two people have already complained.

Good.