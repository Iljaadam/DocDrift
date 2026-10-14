# Word counts

`drift_demo` counts exact word occurrences. Examples read their input as a
JSON array of strings from the `DOCDRIFT_INPUT` environment variable.

## Quickstart

Count each distinct word and print the counts as JSON:

```python
import json
import os

from drift_demo import WordCounter

words = json.loads(os.environ["DOCDRIFT_INPUT"])
result = WordCounter().tally(words)
print(json.dumps(result, sort_keys=True))
```

## Summary

Report how many distinct words there are and the total number of words:

```python
import json
import os

from drift_demo import WordCounter

words = json.loads(os.environ["DOCDRIFT_INPUT"])
counts = WordCounter().count(words)
result = {"distinct": len(counts), "total": sum(counts.values())}
print(json.dumps(result, sort_keys=True))
```
