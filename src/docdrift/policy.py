"""Conservative static defenses for a replacement of one Markdown code span.

These checks establish a narrow patch boundary, not semantic equivalence or
behavioral verification. Frozen checks and fresh execution remain mandatory.
"""

from __future__ import annotations

import ast
import builtins
import re
from collections import Counter

from .markdown import extract_examples


class PolicyError(ValueError):
    """The proposed replacement violates a static patch constraint."""


def _name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _imports(tree: ast.AST) -> tuple[Counter[str], set[str]]:
    modules: Counter[str] = Counter()
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules[alias.name.split(".")[0]] += 1
                aliases.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            modules[(node.module or "").split(".")[0]] += 1
            aliases.update(alias.asname or alias.name for alias in node.names)
    return modules, aliases


def _api_calls(tree: ast.AST, imports: set[str]) -> int:
    # Values assigned from API calls retain their origin for method calls.
    derived = set(imports)
    for _ in range(3):
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.Call):
                if _name(node.value.func).split(".")[0] in derived:
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    derived.update(t.id for target in targets for t in ast.walk(target) if isinstance(t, ast.Name))
    return sum(
        _name(node.func).split(".")[0] in derived
        for node in ast.walk(tree) if isinstance(node, ast.Call)
    )


def _literal(node: ast.AST) -> bool:
    try:
        ast.literal_eval(node)
        return True
    except (ValueError, TypeError, SyntaxError):
        return False


def _literal_names(tree: ast.AST) -> set[str]:
    """Recognize obvious scalar constants without pretending to interpret code."""
    assignments: dict[str, list[ast.AST]] = {}
    other_stores: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and node.value is not None:
                    assignments.setdefault(target.id, []).append(node.value)
                else:
                    other_stores.update(t.id for t in ast.walk(target) if isinstance(t, ast.Name))
        elif isinstance(node, (ast.AugAssign, ast.NamedExpr)):
            other_stores.update(t.id for t in ast.walk(node.target) if isinstance(t, ast.Name))
        elif isinstance(node, (ast.For, ast.AsyncFor, ast.comprehension)):
            other_stores.update(t.id for t in ast.walk(node.target) if isinstance(t, ast.Name))
        elif isinstance(node, ast.arg):
            other_stores.add(node.arg)
    constants: set[str] = set()
    for _ in range(len(assignments) + 1):
        for name, values in assignments.items():
            if name in other_stores:
                continue
            if all(
                isinstance(value, ast.Constant)
                or isinstance(value, ast.Name) and value.id in constants
                for value in values
            ):
                constants.add(name)
    return constants


def _dynamic_prints(tree: ast.AST) -> int:
    constants = _literal_names(tree)
    return sum(
        any(not _literal(arg) and not (isinstance(arg, ast.Name) and arg.id in constants) for arg in node.args)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and _name(node.func) in {"print", "builtins.print"}
    )


def _skips(tree: ast.AST, code: str) -> Counter[str]:
    result: Counter[str] = Counter()
    aliases = _import_aliases(tree)
    for node in ast.walk(tree):
        name = _resolve(_name(node), aliases)
        if name.rsplit(".", 1)[-1].lower() in {"skip", "skipif", "skiptest", "importorskip", "xfail"}:
            result[name.lower()] += 1
    result.update(match.group(0).lower() for match in re.finditer(r"(?im)^\s*#.*(?:doctest\s*:.*\+SKIP|\bskip\b)", code))
    return result


def _import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name.split(".")[0]] = alias.name if alias.asname else alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return aliases


def _resolve(name: str, aliases: dict[str, str]) -> str:
    head, _, tail = name.partition(".")
    return aliases.get(head, head) + (f".{tail}" if tail else "")


def _swallowing_handlers(tree: ast.AST) -> Counter[str]:
    result: Counter[str] = Counter()
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            # Requiring a final raise is deliberately strict: an obscure nested
            # branch does not demonstrate that every exception path propagates.
            if not node.body or not isinstance(node.body[-1], ast.Raise):
                result[ast.dump(node, include_attributes=False)] += 1
    return result


def _exit_calls(tree: ast.AST) -> Counter[str]:
    names = {"exit", "quit", "sys.exit", "os._exit", "builtins.exit", "builtins.quit"}
    aliases = _import_aliases(tree)
    return Counter(
        _resolve(_name(n.func), aliases) for n in ast.walk(tree)
        if isinstance(n, ast.Call) and _resolve(_name(n.func), aliases) in names
    )


def _premature_exits(tree: ast.AST) -> Counter[str]:
    result: Counter[str] = Counter()
    for node in ast.walk(tree):
        for _, value in ast.iter_fields(node):
            if not isinstance(value, list) or not value or not all(isinstance(item, ast.stmt) for item in value):
                continue
            for statement in value[:-1]:
                if isinstance(statement, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
                    result[ast.dump(statement, include_attributes=False)] += 1
                elif isinstance(statement, ast.If) and isinstance(statement.test, ast.Constant):
                    active = statement.body if statement.test.value else statement.orelse
                    if active and isinstance(active[-1], (ast.Return, ast.Raise, ast.Break, ast.Continue)):
                        result[ast.dump(statement, include_attributes=False)] += 1
    return result


def _check_operations(original: str, replacement: str) -> None:
    before, after = ast.parse(original), ast.parse(replacement)
    if _skips(after, replacement) - _skips(before, original):
        raise PolicyError("inserted skips are forbidden")
    if _swallowing_handlers(after) - _swallowing_handlers(before):
        raise PolicyError("new exception swallowing is forbidden")
    if _exit_calls(after) - _exit_calls(before) or _premature_exits(after) - _premature_exits(before):
        raise PolicyError("new unconditional early exits are forbidden")
    original_imports, original_aliases = _imports(before)
    replacement_imports, replacement_aliases = _imports(after)
    if original_imports - replacement_imports:
        raise PolicyError("meaningful imported package operations must remain")
    if _api_calls(after, replacement_aliases) < _api_calls(before, original_aliases):
        raise PolicyError("meaningful API operations must remain")
    if _dynamic_prints(before) and not _dynamic_prints(after):
        raise PolicyError("hardcoded-only output cannot replace meaningful output")
    # Import-free examples must retain at least the same number of calls other
    # than display/conversion builtins. Frozen checks decide the actual behavior.
    nonoperations = set(dir(builtins))
    meaningful_before = sum(
        _name(n.func) not in nonoperations for n in ast.walk(before) if isinstance(n, ast.Call)
    )
    meaningful_after = sum(
        _name(n.func) not in nonoperations for n in ast.walk(after) if isinstance(n, ast.Call)
    )
    if meaningful_after < meaningful_before:
        raise PolicyError("meaningful operations cannot be removed")


def apply_replacement(path: str, original: bytes, example_id: str, original_hash: str, replacement: str) -> bytes:
    """Apply a proposal inside one supported fence, retaining all other bytes.

    The caller must supply a selected Markdown path from its frozen run inputs.
    This function cannot authorize a repository file or change a profile/check.
    """
    if not path.lower().endswith(".md"):
        raise PolicyError("only selected Markdown paths can be patched")
    inventory = extract_examples(path, original)
    selected = next((example for example in inventory if example.id == example_id), None)
    if selected is None:
        raise PolicyError("unknown target example")
    if selected.source_hash != original_hash:
        raise PolicyError("stale original code hash")
    if selected.status != "candidate":
        raise PolicyError(f"unsupported target: {selected.reason}")
    if not replacement.strip():
        raise PolicyError("example deletion or empty replacement is forbidden")
    if "\x00" in replacement:
        raise PolicyError("NUL bytes are forbidden")
    # Reject even a fence hidden in a Python multiline string: it would escape
    # the selected span when rendered as Markdown.
    if re.search(r"(?m)^[ \t]*(?:`{3,}|~{3,})", replacement):
        raise PolicyError("replacement must not introduce Markdown fences")
    normal = replacement.replace("\r\n", "\n").replace("\r", "\n")
    if not normal.endswith("\n"):
        normal += "\n"
    newline = "\r\n" if "\r\n" in selected.code else "\n"
    encoded = normal.replace("\n", newline).encode("utf-8")
    patched = original[:selected.content_start] + encoded + original[selected.content_end:]
    revised = extract_examples(path, patched)
    if [(e.id, e.language) for e in revised] != [(e.id, e.language) for e in inventory]:
        raise PolicyError("example inventory or language changed")
    revised_selected = next(e for e in revised if e.id == example_id)
    if revised_selected.status != "candidate":
        raise PolicyError(f"unsupported replacement: {revised_selected.reason}")
    for old, new in zip(inventory, revised, strict=True):
        if old.id != example_id and old.source_hash != new.source_hash:
            raise PolicyError("non-target example changed")
    _check_operations(selected.code, revised_selected.code)
    return patched
