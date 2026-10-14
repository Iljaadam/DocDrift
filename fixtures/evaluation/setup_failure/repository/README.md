# Owned missing build prerequisite

The declared offline PEP 517 installation requires
`REQUIRED_BUILD_INPUT.json`. That input is intentionally absent from the
frozen snapshot. The current DocDrift slice rejects this setup recipe before
executing the backend. Changing this documentation example cannot supply the
missing prerequisite, and source-tree imports would bypass the declared setup.

```python
import json
import os

from drift_demo import TokenIdentity

words = json.loads(os.environ["DOCDRIFT_INPUT"])
result = TokenIdentity().echo(words)
print(json.dumps(result, sort_keys=True))
```
