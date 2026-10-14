# Token ordering

`drift_demo` sorts tokens. Examples read a JSON array of strings from
`DOCDRIFT_INPUT`.

## Descending order

Print the tokens in descending order, keeping duplicates and exact string values:

```python
import json
import os

from drift_demo import TokenOrderer

words = json.loads(os.environ["DOCDRIFT_INPUT"])
result = TokenOrderer().sort(words, reverse=True)
print(json.dumps(result, sort_keys=True))
```

## Ascending order with first token

Print the tokens in ascending order and the first one, or `null` for an empty input:

```python
import json
import os

from drift_demo import TokenOrderer

words = json.loads(os.environ["DOCDRIFT_INPUT"])
ordered = TokenOrderer().sort(words, descending=False)
result = {"ordered": ordered, "first": ordered[0] if ordered else None}
print(json.dumps(result, sort_keys=True))
```
