# Owned secret and service requirement

This example requires a credential and an external service. It is deliberately
outside DocDrift's standalone, offline support. Never supply the credential or
attempt its request during fixture inventory.

```python
import os
import urllib.request

api_key = os.environ["DEMO_API_KEY"]
request = urllib.request.Request(
    "https://example.invalid/events",
    headers={"Authorization": f"Bearer {api_key}"},
)
with urllib.request.urlopen(request) as response:
    print(response.read().decode())
```
