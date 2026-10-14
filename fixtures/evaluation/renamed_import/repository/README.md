# Owned renamed-import example

The API renamed the imported class from `TextJoiner` to `TokenJoiner`.
The documented behavior joins exact input strings with `|` between them.
Inputs arrive as a JSON array in `DOCDRIFT_INPUT`.

```python
import json
import os

from drift_demo import TextJoiner

words = json.loads(os.environ["DOCDRIFT_INPUT"])
result = TextJoiner().join(words)
print(json.dumps(result, sort_keys=True))
```

The neighboring example already imports the current API and reports joined
text and its length.

```python
import json
import os

from drift_demo import TokenJoiner

words = json.loads(os.environ["DOCDRIFT_INPUT"])
joined = TokenJoiner().join(words)
result = {"joined": joined, "length": len(joined)}
print(json.dumps(result, sort_keys=True))
```
