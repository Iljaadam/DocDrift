import json
import os

from drift_demo import OccurrenceIndex

words = json.loads(os.environ["DOCDRIFT_INPUT"])
result = OccurrenceIndex().positions(words, include_empty=True)
print(json.dumps(result, sort_keys=True))
