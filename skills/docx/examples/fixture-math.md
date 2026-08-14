# Math Fixture

Inline math renders as a real object: $E = mc^2$ and $\mathbf{x}_t$ subscript notation.

A standalone display formula, alone on its own paragraph between blank lines:

$$
\sum_{i=1}^{n} x_i = \frac{n(n+1)}{2}
$$

A formula inside **bold text $\alpha + \beta$ here** — it still renders as a real math
object, just without the bold styling (honest scope, TASK 031 §2).

Currency is not math: $5 and $10, and an escaped dollar \$5 is never a delimiter either.

A fenced code block is inert — the `$x$` inside it must survive as literal text:

```
formula-looking text: $x$ stays literal in a fence
```

An inline code span is inert too: `$y$` stays literal.

A Pandoc-style numbered equation table (the reference document's actual shape):

|  | $$y = mx + b$$ |  | (1) |
|---|---|---|---|

An intentionally malformed formula, to exercise degrade-and-warn / `--strict-math`: $\left($
