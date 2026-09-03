I spent Tuesday chasing down a bug that turned out to be a stale DNS cache on one of the build agents. Three hours, gone. The fix ended up being one line in the Dockerfile.

What gets me is that the agent had been flaking on and off for a week and nobody filed anything, because "it passes on retry" is the kind of sentence that kills an investigation instead of starting one.

We now fail the build loudly the moment a lookup takes longer than 500 ms. Two people have already complained. Good.