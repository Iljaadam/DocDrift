import json
import os

from drift_demo import TokenOrderer

words = json.loads(os.environ["DOCDRIFT_INPUT"])
result = TokenOrderer().sort(words, descending=True)
print(json.dumps(result, sort_keys=True))
