import hashlib

import pytest

from docdrift.markdown import extract_examples


def test_inventory_exact_utf8_spans_and_stable_ids():
    content = "# Café\n\n```python\nfrom demo import greet\nprint(greet('é'))\n```\n\n~~~json\n{}\n~~~\n".encode()
    python, other = extract_examples("README.md", content)
    assert (python.start_line, python.end_line) == (3, 6)
    assert python.status == "candidate"
    raw = content[python.content_start:python.content_end]
    assert raw == "from demo import greet\nprint(greet('é'))\n".encode()
    assert python.source_hash == hashlib.sha256(raw).hexdigest()
    assert other.status == "unsupported"
    assert other.language == "json"
    changed = content.replace(b"greet('", b"hello('")
    assert [e.id for e in extract_examples("README.md", changed)] == [python.id, other.id]
    assert extract_examples("OTHER.md", content)[0].id != python.id


def test_crlf_and_longer_tilde_delimiters_are_preserved():
    content = b"text\r\n~~~~python\r\nprint('hello')\r\n~~~~~\r\n"
    example, = extract_examples("README.md", content)
    assert example.status == "candidate"
    assert example.code == "print('hello')\r\n"
    assert content[example.content_start:example.content_end] == example.code.encode()
    assert (example.start_line, example.end_line) == (2, 4)


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        ("client.query()", "dependent fragment"),
        ("...", "placeholder"),
        ("def helper():", "incomplete"),
        (">>> print(1)", "REPL"),
        ("%load_ext dotenv", "IPython"),
        ("input('name?')", "interactive"),
        ("from getpass import getpass\ngetpass()", "interactive"),
        ("import requests\nrequests.get('https://example.com')", "network"),
        ("import os\nos.environ['API_KEY']", "secret"),
        ("import os\nos.getenv('SERVICE_TOKEN')", "secret"),
        ("import torch\nx = torch.zeros(1).cuda()", "GPU"),
        ("from .client import Client", "relative import"),
        ("await operation()", "syntax"),
        ("", "empty"),
    ],
)
def test_unsupported_examples_are_inventoried(code, reason):
    example, = extract_examples("README.md", f"```python\n{code}\n```\n".encode())
    assert example.status == "unsupported"
    assert reason in example.reason


@pytest.mark.parametrize(
    "document",
    [
        b"- ```python\n  print(1)\n  ```\n",
        b"> ```python\n> print(1)\n> ```\n",
        b"  ```python\n  print(1)\n  ```\n",
    ],
)
def test_nested_and_indented_fences_are_inventoried_but_not_patchable(document):
    example, = extract_examples("README.md", document)
    assert example.status == "unsupported"
    assert "unsafe" in example.reason
    assert document[example.content_start:example.content_end] == example.code.encode()


def test_unclosed_and_over_limit_fences_are_retained():
    unclosed, = extract_examples("README.md", b"```python\nprint(1)\n")
    assert "unclosed" in unclosed.reason
    assert unclosed.code == "print(1)\n"
    limited, = extract_examples("README.md", b"```python\nprint(1)\nprint(2)\n```\n", max_lines=1)
    assert limited.status == "unsupported"
    assert "limit" in limited.reason
    with pytest.raises(ValueError, match="positive"):
        extract_examples("README.md", b"", max_lines=0)


def test_quote_prefixed_fence_does_not_close_a_top_level_fence():
    example, = extract_examples("README.md", b"```python\nprint(1)\n> ```\n")
    assert "unclosed" in example.reason
    assert example.code.endswith("> ```\n")


def test_function_parameters_and_local_bindings_are_supported():
    code = b"```python\ndef greet(name):\n    return name.upper()\nprint(greet('world'))\n```\n"
    assert extract_examples("README.md", code)[0].status == "candidate"


def test_unprofiled_candidate_is_only_a_structural_classification():
    example, = extract_examples("README.md", b"```python\nfrom absent_package import api\nprint(api())\n```\n")
    assert example.status == "candidate"
    assert example.reason is None
