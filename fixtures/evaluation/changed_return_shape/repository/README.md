# Owned changed-return-shape example

This example promises a scalar JSON integer: the total number of input tokens.
The current API returns a statistics dictionary instead of that former scalar.
Inputs are JSON arrays in `DOCDRIFT_INPUT`.

```python
import json
import os

from drift_demo import TokenStats

words = json.loads(os.environ["DOCDRIFT_INPUT"])
result = TokenStats().measure(words)
print(json.dumps(result, sort_keys=True))
```
