"""Fence inventory with exact byte spans; extraction never authorizes execution."""

from __future__ import annotations

import ast
import builtins
import hashlib
import re
from dataclasses import dataclass

from markdown_it import MarkdownIt


@dataclass(frozen=True)
class Example:
    id: str
    path: str
    language: str
    start_line: int
    end_line: int
    content_start: int
    content_end: int
    source_hash: str
    code: str
    status: str
    reason: str | None


_PYTHON_LANGUAGES = {"python", "python3", "py"}
_NETWORK_MODULES = {
    "requests", "httpx", "aiohttp", "socket", "grpc", "boto3", "botocore",
    "openai", "anthropic", "nebius", "redis", "psycopg", "psycopg2",
    "pymongo", "paramiko", "ftplib", "smtplib", "websockets",
}
_INTERACTIVE_MODULES = {"tkinter", "streamlit", "gradio"}


def _qualified_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _qualified_name(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _unsupported_python(code: str, path: str) -> str | None:
    if not code.strip():
        return "empty example"
    if re.search(r"(?m)^[ \t]*(?:>>>|\.\.\.[ \t]+|%[A-Za-z]|![A-Za-z])", code):
        return "REPL/IPython syntax is outside standalone Python support"
    try:
        tree = ast.parse(code, filename=path)
        # ast.parse accepts constructs such as top-level await; execution does not.
        compile(tree, path, "exec")
    except (SyntaxError, ValueError) as exc:
        return f"incomplete or unsupported Python syntax: {exc.msg if isinstance(exc, SyntaxError) else exc}"

    bound = set(dir(builtins)) | {"__name__", "__file__", "__doc__", "__package__"}
    loaded: set[str] = set()
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            if isinstance(node, ast.ImportFrom) and node.level:
                return "relative import requires omitted package context"
            for module in modules:
                root = module.split(".")[0]
                if root in _NETWORK_MODULES or module.startswith("urllib.request"):
                    return "external network, secret, or service dependency"
                if root in _INTERACTIVE_MODULES:
                    return "interactive application dependency"
                if root in {"subprocess", "cupy", "pycuda"}:
                    return "external process or GPU workload"
            for alias in node.names:
                if alias.name == "*":
                    return "wildcard import makes standalone dependencies ambiguous"
                name = alias.asname or (alias.name.split(".")[0] if isinstance(node, ast.Import) else alias.name)
                bound.add(name)
                aliases[name] = alias.name if isinstance(node, ast.Import) else f"{node.module}.{alias.name}"
        elif isinstance(node, ast.Name):
            if isinstance(node.ctx, (ast.Store, ast.Del)):
                bound.add(node.id)
            elif isinstance(node.ctx, ast.Load):
                loaded.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            bound.add(node.name)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            bound.add(node.name)
        elif isinstance(node, (ast.MatchAs, ast.MatchStar)) and node.name:
            bound.add(node.name)
        elif isinstance(node, ast.Constant) and node.value is Ellipsis:
            return "ellipsis placeholder or dependent fragment"

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _qualified_name(node.func)
        head, _, tail = name.partition(".")
        resolved = aliases.get(head, head) + (f".{tail}" if tail else "")
        if resolved in {"input", "getpass.getpass", "builtins.input"}:
            return "interactive input is unsupported"
        if resolved in {"os.system", "os.popen", "uvicorn.run"} or resolved.endswith(".serve_forever"):
            return "external process or persistent service"
        if resolved.startswith(("urllib.request.", "socket.")):
            return "external network dependency"
        if (isinstance(node.func, ast.Attribute) and node.func.attr == "cuda") or any(
            kw.arg == "device" and isinstance(kw.value, ast.Constant)
            and isinstance(kw.value.value, str) and kw.value.value.startswith("cuda")
            for kw in node.keywords
        ):
            return "GPU workload is unsupported"
        if resolved in {"os.getenv", "os.environ.get", "os.environ.__getitem__"} and node.args:
            key = node.args[0]
            if isinstance(key, ast.Constant) and isinstance(key.value, str) and _secret_name(key.value):
                return "secret-dependent environment input"
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and _qualified_name(node.value) == "os.environ":
            if isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str) and _secret_name(node.slice.value):
                return "secret-dependent environment input"
    missing = sorted(loaded - bound)
    if missing:
        return f"dependent fragment: undefined name {missing[0]!r}"
    if not any(isinstance(node, (ast.Call, ast.Assign, ast.AnnAssign, ast.AugAssign, ast.Import, ast.ImportFrom)) for node in ast.walk(tree)):
        return "incomplete sketch has no runnable operation"
    return None


def _secret_name(value: str) -> bool:
    return bool(re.search(r"(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)", value, re.IGNORECASE))


def extract_examples(path: str, content: bytes, max_lines: int = 200) -> list[Example]:
    """Inventory all CommonMark fences, including unsupported ones.

    Offsets select only the exact raw code bytes. IDs use the document path and
    fence ordinal, so an edit inside a fence retains its identity. ``candidate``
    means structurally supported; a frozen external run profile is still needed.
    """
    if max_lines < 1:
        raise ValueError("max_lines must be positive")
    document = content.decode("utf-8")
    lines = content.splitlines(keepends=True)
    offsets = [0]
    for line in lines:
        offsets.append(offsets[-1] + len(line))
    examples: list[Example] = []
    fences = (token for token in MarkdownIt("commonmark").parse(document) if token.type == "fence")
    for ordinal, token in enumerate(fences, 1):
        assert token.map is not None
        start, end = token.map
        marker = token.markup[0]
        width = len(token.markup)
        opener = lines[start].rstrip(b"\r\n")
        direct_opener = re.match(rb"^(`{3,}|~{3,})", opener)
        # A quote-prefixed marker is not a closing fence for a top-level token.
        # Nested tokens are always unsupported, but their raw spans are useful.
        prefix = rb"^[ ]{0,3}" if token.level == 0 and direct_opener else rb"^[\t >]*"
        closing_pattern = prefix + re.escape(marker.encode()) + b"{" + str(width).encode() + rb",}[ \t]*(?:\r?\n)?$"
        closed = end > start + 1 and bool(re.fullmatch(closing_pattern, lines[end - 1]))
        body_end = end - 1 if closed else end
        content_start, content_end = offsets[start + 1], offsets[body_end]
        raw_code = content[content_start:content_end]
        code = raw_code.decode("utf-8")
        language = token.info.strip().split()[0].lower() if token.info.strip() else ""
        reason: str | None = None
        if token.level != 0 or direct_opener is None:
            reason = "nested or indented fence has unsafe exact-code patch boundaries"
        elif not closed:
            reason = "unclosed fence cannot be safely patched"
        elif language not in _PYTHON_LANGUAGES:
            reason = "non-Python or REPL/IPython fence is unsupported"
        elif body_end - start - 1 > max_lines:
            reason = f"example exceeds {max_lines}-line limit"
        else:
            reason = _unsupported_python(code, path)
        identifier = "ex_" + hashlib.sha256(f"{path}\0{ordinal}".encode()).hexdigest()[:20]
        examples.append(Example(
            id=identifier, path=path, language=language, start_line=start + 1,
            end_line=end, content_start=content_start, content_end=content_end,
            source_hash=hashlib.sha256(raw_code).hexdigest(), code=code,
            status="unsupported" if reason else "candidate", reason=reason,
        ))
    return examples
