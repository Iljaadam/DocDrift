import json
import os

from drift_demo import WordCounter

words = json.loads(os.environ["DOCDRIFT_INPUT"])
result = WordCounter().count(words)
print(json.dumps(result, sort_keys=True))
