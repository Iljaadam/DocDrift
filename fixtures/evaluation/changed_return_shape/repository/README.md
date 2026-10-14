# Token statistics

`drift_demo` measures token collections. The example reads a JSON array of
strings from `DOCDRIFT_INPUT`.

## Total tokens

Print the total number of input tokens as a JSON integer:

```python
import json
import os

from drift_demo import TokenStats

words = json.loads(os.environ["DOCDRIFT_INPUT"])
result = TokenStats().measure(words)
print(json.dumps(result, sort_keys=True))
```
