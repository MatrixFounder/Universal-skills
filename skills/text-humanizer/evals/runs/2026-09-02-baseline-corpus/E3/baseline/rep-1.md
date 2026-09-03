Tuesday I burned three hours chasing a bug that turned out to be nothing more than a stale DNS cache on one of the build agents. The actual fix was one line in the Dockerfile.

What gets me is that the agent had been flaking on and off for a whole week and nobody bothered to file anything, because "it passes on retry" is exactly the kind of line that shuts down an investigation instead of kicking one off.

So now the build fails loudly whenever a lookup takes longer than 500 ms. Two people have already complained about it. Good.