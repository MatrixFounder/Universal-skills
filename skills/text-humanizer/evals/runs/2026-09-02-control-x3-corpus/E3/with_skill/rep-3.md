I spent Tuesday chasing a bug that turned out to be a stale DNS cache on one of the build agents. Three hours. The fix was a single line in the Dockerfile.

What annoys me: the agent had been failing on and off for a week, and nobody filed anything. "It passes on retry" is the kind of sentence that ends an investigation before it starts.

We now fail the build loudly when a lookup takes longer than 500 ms. Two people have already complained. Good.