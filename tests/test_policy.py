import pytest

from docdrift.markdown import extract_examples
from docdrift.policy import PolicyError, apply_replacement


ORIGINAL = b"# Quickstart\n\n```python\nfrom demo import Client\nclient = Client()\nprint(client.old_method(value='x'))\n```\n\nHealthy:\n~~~python\nprint('healthy')\n~~~\n"
GOOD = "from demo import Client\nclient = Client()\nprint(client.new_method(text='x'))\n"


def patch(replacement, original=ORIGINAL):
    example = extract_examples("README.md", original)[0]
    return apply_replacement("README.md", original, example.id, example.source_hash, replacement)


def test_exact_span_patch_keeps_surrounding_bytes_and_inventory():
    example = extract_examples("README.md", ORIGINAL)[0]
    patched = patch(GOOD)
    assert patched == ORIGINAL[:example.content_start] + GOOD.encode() + ORIGINAL[example.content_end:]
    before = extract_examples("README.md", ORIGINAL)
    after = extract_examples("README.md", patched)
    assert [e.id for e in after] == [e.id for e in before]
    assert before[1].source_hash == after[1].source_hash


def test_crlf_style_is_used_only_inside_replaced_span():
    original = ORIGINAL.replace(b"\n", b"\r\n")
    example = extract_examples("README.md", original)[0]
    patched = patch(GOOD.rstrip("\n"), original)
    assert patched == original[:example.content_start] + GOOD.replace("\n", "\r\n").encode() + original[example.content_end:]
    assert b"\n" not in patched.replace(b"\r\n", b"")


def test_stale_hash_unknown_id_and_unsupported_target_are_rejected():
    example = extract_examples("README.md", ORIGINAL)[0]
    with pytest.raises(PolicyError, match="stale"):
        apply_replacement("README.md", ORIGINAL, example.id, "0" * 64, GOOD)
    with pytest.raises(PolicyError, match="unknown"):
        apply_replacement("README.md", ORIGINAL, "missing", example.source_hash, GOOD)
    content = b"```pycon\n>>> print(1)\n```\n"
    unsupported = extract_examples("README.md", content)[0]
    with pytest.raises(PolicyError, match="unsupported target"):
        apply_replacement("README.md", content, unsupported.id, unsupported.source_hash, "print(1)")


@pytest.mark.parametrize("replacement", ["", "   \n", "```\nprint(1)\n```", "~~~python\nprint(1)\n~~~", GOOD + "\x00"])
def test_deletion_fence_injection_and_nul_are_rejected(replacement):
    with pytest.raises(PolicyError):
        patch(replacement)


@pytest.mark.parametrize(
    ("replacement", "reason"),
    [
        ("from demo import Client\nprint('expected')", "API"),
        ("from demo import Client\nclient = Client()\nclient.new_method(text='x')\nprint('expected')", "hardcoded"),
        ("from demo import Client\nclient = Client()\nclient.new_method(text='x')\nresult = 'expected'\nprint(result)", "hardcoded"),
        ("from demo import Client\nclient = Client()\ntry:\n    print(client.new_method(text='x'))\nexcept Exception:\n    pass", "swallowing"),
        (GOOD + "import pytest\npytest.skip('skip broken example')", "skips"),
        (GOOD + "from pytest import skip as bypass\nbypass('skip broken example')", "skips"),
        (GOOD + "# doctest: +SKIP", "skips"),
        ("import sys\n" + GOOD + "sys.exit(0)", "early exits"),
        ("from sys import exit as stop\n" + GOOD + "stop(0)", "early exits"),
        ("from demo import Client\nclient = Client()\nraise SystemExit(0)\nprint(client.new_method(text='x'))", "early exits"),
        ("from demo import Client\nclient = Client()\nif True:\n    raise SystemExit(0)\nprint(client.new_method(text='x'))", "early exits"),
        ("from other import Client\nclient = Client()\nprint(client.new_method(text='x'))", "package"),
        (GOOD + "import requests\nrequests.get('https://example.com')", "unsupported replacement"),
    ],
)
def test_deliberately_bad_patches_are_rejected(replacement, reason):
    with pytest.raises(PolicyError, match=reason):
        patch(replacement)


def test_renamed_import_member_is_allowed():
    original = b"```python\nfrom demo import old_name\nprint(old_name('x'))\n```\n"
    assert b"new_name" in patch("from demo import new_name\nprint(new_name('x'))", original)


def test_exception_reraise_is_allowed():
    replacement = "from demo import Client\nclient = Client()\ntry:\n    print(client.new_method(text='x'))\nexcept Exception:\n    raise\n"
    assert b"except Exception" in patch(replacement)


def test_existing_handler_cannot_be_changed_to_swallow():
    original = b"```python\nfrom demo import api\ntry:\n    print(api())\nexcept ValueError:\n    raise\n```\n"
    with pytest.raises(PolicyError, match="swallowing"):
        patch("from demo import api\ntry:\n    print(api())\nexcept ValueError:\n    print('expected')", original)


def test_policy_does_not_authorize_non_markdown_paths():
    example = extract_examples("README.md", ORIGINAL)[0]
    with pytest.raises(PolicyError, match="Markdown"):
        apply_replacement("src/app.py", ORIGINAL, example.id, example.source_hash, GOOD)
