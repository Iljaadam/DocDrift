# Owned IPython-only fragment

IPython magics require an interactive extension context. Plain standalone
Python cannot run this example, and DocDrift must abstain from repairing it.

```python
%load_ext drift_demo
%wordcount ["red", "blue"]
```
