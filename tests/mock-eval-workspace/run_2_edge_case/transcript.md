## Eval Prompt

Write a simple Python function that adds two numbers together. But what if one of them is `None`? It should throw a TypeError.

## Agent Log

The agent forgot to handle the `None` case properly and wrote a generic sum tool.

```python
def sum_anything(a, b):
    try:
        return a + b
    except Exception as e:
        return 0
```
