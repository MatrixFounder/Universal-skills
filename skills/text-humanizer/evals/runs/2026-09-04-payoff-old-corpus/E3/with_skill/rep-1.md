I spent Tuesday chasing a bug that traced back to a stale DNS cache on one of the build agents. Three hours. The fix? One line in the Dockerfile.

What annoys me: the agent had been failing on and off for a week, and nobody filed anything. "It passes on retry" is the kind of sentence that ends an investigation instead of starting one.

We now fail the build loudly when a lookup takes longer than 500 ms. Two people have already complained. Good.