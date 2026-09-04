Tuesday ate three hours of my day on a bug that turned out to be nothing more than a stale DNS cache on one of the build agents. The actual fix was one line in the Dockerfile.

What bugs me is that this agent had been flaking on and off for a whole week before that, and nobody ever filed anything on it. "It passes on retry" is exactly the kind of line that shuts an investigation down before it starts.

So now the build fails loudly whenever a lookup takes longer than 500ms. Two people have already complained about it. Good.