# Drift demo: word counts

This owned, offline fixture deliberately demonstrates documentation that still
calls the former `tally` method. The installed package exposes `count` instead.
Inputs are supplied as a JSON array of strings in `DOCDRIFT_INPUT`.

## Quickstart with the outdated method

```python
import json
import os

from drift_demo import WordCounter

words = json.loads(os.environ["DOCDRIFT_INPUT"])
result = WordCounter().tally(words)
print(json.dumps(result, sort_keys=True))
```

## Healthy summary example

```python
import json
import os

from drift_demo import WordCounter

words = json.loads(os.environ["DOCDRIFT_INPUT"])
counts = WordCounter().count(words)
result = {"distinct": len(counts), "total": sum(counts.values())}
print(json.dumps(result, sort_keys=True))
```
