import json
import os

from drift_demo import TokenStats

words = json.loads(os.environ["DOCDRIFT_INPUT"])
result = TokenStats().measure(words)["total"]
print(json.dumps(result, sort_keys=True))
