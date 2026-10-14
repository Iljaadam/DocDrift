# Owned changed-keyword example

The ordering API now accepts `descending` where the previous API accepted
`reverse`. The target example promises tokens in descending order, preserving
duplicates and exact string values. Inputs are JSON arrays in `DOCDRIFT_INPUT`.

```python
import json
import os

from drift_demo import TokenOrderer

words = json.loads(os.environ["DOCDRIFT_INPUT"])
result = TokenOrderer().sort(words, reverse=True)
print(json.dumps(result, sort_keys=True))
```

This healthy neighbor reports ascending token order and its first value,
using `None` for an empty collection.

```python
import json
import os

from drift_demo import TokenOrderer

words = json.loads(os.environ["DOCDRIFT_INPUT"])
ordered = TokenOrderer().sort(words, descending=False)
result = {"ordered": ordered, "first": ordered[0] if ordered else None}
print(json.dumps(result, sort_keys=True))
```
