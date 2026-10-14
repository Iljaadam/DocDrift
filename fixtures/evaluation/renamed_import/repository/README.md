# Joining tokens

`drift_demo` joins exact input strings with `|` between them. Examples read a
JSON array of strings from `DOCDRIFT_INPUT`.

## Quickstart

Print the joined text:

```python
import json
import os

from drift_demo import TextJoiner

words = json.loads(os.environ["DOCDRIFT_INPUT"])
result = TextJoiner().join(words)
print(json.dumps(result, sort_keys=True))
```

## Joined text and length

Print the joined text together with its length:

```python
import json
import os

from drift_demo import TokenJoiner

words = json.loads(os.environ["DOCDRIFT_INPUT"])
joined = TokenJoiner().join(words)
result = {"joined": joined, "length": len(joined)}
print(json.dumps(result, sort_keys=True))
```
