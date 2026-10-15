# Token positions

`drift_demo` provides small text utilities. Examples read a JSON array of strings
from the `DOCDRIFT_INPUT` environment variable.

## Occurrence index

Print a JSON object mapping every exact token to its zero-based input positions.
Preserve empty strings, whitespace, case, and Unicode characters as distinct
values. Repeated tokens have several positions; an empty input produces `{}`.

```python
import json
import os

from drift_demo import OccurrenceIndex

words = json.loads(os.environ["DOCDRIFT_INPUT"])
result = OccurrenceIndex().build(words)
print(json.dumps(result, sort_keys=True))
```

## Text summary

Print the number of tokens and the total number of characters in the input:

```python
import json
import os

from drift_demo import TokenMetrics

words = json.loads(os.environ["DOCDRIFT_INPUT"])
result = TokenMetrics().measure(words)
print(json.dumps(result, sort_keys=True))
```
