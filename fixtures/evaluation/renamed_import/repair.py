import json
import os

from drift_demo import TokenJoiner

words = json.loads(os.environ["DOCDRIFT_INPUT"])
result = TokenJoiner().join(words)
print(json.dumps(result, sort_keys=True))
