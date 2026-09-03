Tuesday ate three hours of my day chasing what turned out to be a stale DNS cache on one of the build agents. The fix was one line in the Dockerfile.

What gets me is that the agent had been flaking for a week straight and nobody filed a thing, because "it passes on retry" is the kind of line that shuts an investigation down instead of opening one.

So now the build fails loudly if a lookup takes longer than 500 ms. Two people have already complained. Good.