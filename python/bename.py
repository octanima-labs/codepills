# CODEPILLS-META-BEGIN
# schema: codepills.tool/v1
# name: bename
# version: 1.0.0
# author: octanima-labs
# description: Safely batch-rename files and directories with counters and name templates.
# repo: https://github.com/octanima-labs/codepills/blob/main/python/bename.py
# license: MIT
# usage: python python/bename.py PATH -n RENAME [OPTIONS]
# tags:
#   - python
#   - cli
#   - rename
# requires:
#   - Python standard library
# platforms:
#   - Linux
#   - macOS
#   - Windows
# CODEPILLS-META-END

"""Batch rename files and directories from a CLI or importable module.

``bename`` builds a complete rename plan before touching the filesystem. It
supports f-string-like placeholders such as ``{NAME}``, safe string operations
derived from ``NAME``, and numeric counters such as ``{<001}`` or ``{>512}``.

Examples:
    Rename one path::

        python bename.py image.png -n "photo_{NAME}"

    Rename a directory's contents recursively with a counter::

        python bename.py . -n "{<001}-{NAME}" -r -s "<size"

    Use ``bn`` as a shell alias for this script::

        bn . -n "{<001}{NAME}" -s "<SIZE"
"""

from __future__ import annotations

import argparse
import ast
import fnmatch
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


COUNTER_PATTERN = re.compile(r"^([<>]?)(\d+)$")
SPLIT_INDEX_PATTERN = re.compile(r"^NAME\.split\[(\d+)]$")
SAFE_STRING_METHODS = {
    "capitalize",
    "casefold",
    "lower",
    "lstrip",
    "removeprefix",
    "removesuffix",
    "replace",
    "rsplit",
    "rstrip",
    "split",
    "strip",
    "swapcase",
    "title",
    "upper",
    "zfill",
}


@dataclass(frozen=True)
class RenamePlan:
    """One planned filesystem rename."""

    source: Path
    target: Path


@dataclass(frozen=True)
class RenameResult:
    """One completed filesystem rename."""

    source: Path
    target: Path


@dataclass(frozen=True)
class _SortSpec:
    field: str
    reverse: bool


class _NameExpressionEvaluator(ast.NodeVisitor):
    """Evaluate a tiny, string-focused subset of Python expressions."""

    def __init__(self, name: str):
        self.name = name

    def evaluate(self, expression: str) -> Any:
        split_match = SPLIT_INDEX_PATTERN.fullmatch(expression.strip())
        if split_match:
            try:
                return self.name.split()[int(split_match.group(1))]
            except IndexError as error:
                raise ValueError(f"NAME.split index out of range: {expression}") from error

        try:
            node = ast.parse(expression, mode="eval")
        except SyntaxError as error:
            raise ValueError(f"invalid template expression: {expression}") from error
        return self.visit(node)

    def visit_Expression(self, node: ast.Expression) -> Any:
        return self.visit(node.body)

    def visit_Name(self, node: ast.Name) -> str:
        if node.id != "NAME":
            raise ValueError(f"unknown template name: {node.id}")
        return self.name

    def visit_Constant(self, node: ast.Constant) -> str | int | None:
        if isinstance(node.value, (str, int)) or node.value is None:
            return node.value
        raise ValueError("template constants may only be strings, integers, or None")

    def visit_Call(self, node: ast.Call) -> Any:
        if not isinstance(node.func, ast.Attribute):
            raise ValueError("template expressions may only call NAME string methods")
        if node.func.attr not in SAFE_STRING_METHODS:
            raise ValueError(f"unsupported NAME method: {node.func.attr}")
        if node.keywords:
            raise ValueError("template method calls do not support keyword arguments")

        value = self.visit(node.func.value)
        if not isinstance(value, str):
            raise ValueError("template methods can only be called on strings")

        args = [self.visit(arg) for arg in node.args]
        try:
            return getattr(value, node.func.attr)(*args)
        except (TypeError, ValueError) as error:
            raise ValueError(f"invalid arguments for NAME.{node.func.attr}()") from error

    def visit_Subscript(self, node: ast.Subscript) -> Any:
        value = self.visit(node.value)
        index = self._slice_value(node.slice)
        try:
            return value[index]
        except (IndexError, KeyError, TypeError) as error:
            raise ValueError("template subscript is invalid or out of range") from error

    def visit_BinOp(self, node: ast.BinOp) -> str:
        if not isinstance(node.op, ast.Add):
            raise ValueError("template expressions only support string concatenation")
        left = self.visit(node.left)
        right = self.visit(node.right)
        if not isinstance(left, str) or not isinstance(right, str):
            raise ValueError("template concatenation only supports strings")
        return left + right

    def _slice_value(self, node: ast.AST) -> int | slice:
        if isinstance(node, ast.Slice):
            lower = self.visit(node.lower) if node.lower else None
            upper = self.visit(node.upper) if node.upper else None
            step = self.visit(node.step) if node.step else None
            return slice(lower, upper, step)
        value = self.visit(node)
        if not isinstance(value, int):
            raise ValueError("template indexes must be integers")
        return value

    def generic_visit(self, node: ast.AST) -> Any:
        raise ValueError(f"unsupported template expression: {type(node).__name__}")


def preview_renames(
    path: str | os.PathLike[str],
    new_name: str,
    exclude: Iterable[str] | None = None,
    recursive: bool = False,
    hidden: bool = False,
    sort: str | None = None,
) -> list[RenamePlan]:
    """Build and validate a rename plan without changing the filesystem.

    Args:
        path: File or directory to rename. With ``recursive=True`` and a
            directory path, the directory's contents are renamed instead.
        new_name: Template used to produce each new basename.
        exclude: Optional fnmatch patterns checked against absolute path,
            root-relative path, and basename.
        recursive: Rename directory contents recursively instead of the root
            directory itself.
        hidden: Include hidden children during recursive scans.
        sort: Optional ``<NAME``, ``>SIZE``, or ``<ext`` style sort expression.
            Sorting is ignored when ``new_name`` has no numeric counter.

    Returns:
        A list of changing source-to-target pairs.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If the template, sort expression, or target plan is invalid.
    """

    root = _absolute_path(path)
    if not root.exists():
        raise FileNotFoundError(root)

    patterns = list(exclude or [])
    candidates = _collect_candidates(root, patterns, recursive, hidden)
    if not candidates:
        return []

    assignment_order = list(candidates)
    if _template_has_counter(new_name) and sort:
        sort_spec = _parse_sort(sort)
        assignment_order.sort(key=lambda item: _sort_key(item, sort_spec), reverse=sort_spec.reverse)

    rendered_names = {
        source: _render_new_basename(source, new_name, index)
        for index, source in enumerate(assignment_order)
    }
    target_cache: dict[Path, Path] = {}

    def target_for(source: Path) -> Path:
        cached = target_cache.get(source)
        if cached is not None:
            return cached
        parent_target = target_for(source.parent) if source.parent in rendered_names else source.parent
        target = parent_target / rendered_names[source]
        target_cache[source] = target
        return target

    all_plans = [RenamePlan(source=source, target=target_for(source)) for source in assignment_order]
    changing_plans = [plan for plan in all_plans if _normcase(plan.source) != _normcase(plan.target)]
    _validate_plan(changing_plans, all_plans)
    return changing_plans


def rename_paths(
    path: str | os.PathLike[str],
    new_name: str,
    exclude: Iterable[str] | None = None,
    recursive: bool = False,
    hidden: bool = False,
    sort: str | None = None,
) -> list[RenameResult]:
    """Rename paths according to a validated plan and return completed results."""

    root = _absolute_path(path)
    plans = preview_renames(root, new_name, exclude, recursive, hidden, sort)
    if not plans:
        return []

    staging_parent = root if recursive and root.is_dir() else root.parent
    staging_dir = Path(tempfile.mkdtemp(prefix=".bename-", dir=str(staging_parent)))
    staged: dict[Path, Path] = {}

    try:
        for index, plan in enumerate(sorted(plans, key=lambda item: _path_depth(item.source), reverse=True)):
            temporary = staging_dir / f"{index}-{plan.source.name}"
            plan.source.rename(temporary)
            staged[plan.source] = temporary

        for plan in sorted(plans, key=lambda item: _path_depth(item.source)):
            temporary = staged[plan.source]
            plan.target.parent.mkdir(parents=True, exist_ok=True)
            temporary.rename(plan.target)
    finally:
        try:
            staging_dir.rmdir()
        except OSError:
            pass

    return [RenameResult(source=plan.source, target=plan.target) for plan in plans]


def render_name(name: str, template: str, index: int = 0) -> str:
    """Render a template against a NAME value and zero-based counter index."""

    return _render_template(template, name, index)


def _absolute_path(path: str | os.PathLike[str]) -> Path:
    expanded = os.path.expanduser(os.fspath(path))
    return Path(os.path.abspath(expanded))


def _collect_candidates(root: Path, patterns: list[str], recursive: bool, hidden: bool) -> list[Path]:
    if recursive and root.is_dir():
        return _collect_recursive(root, root, patterns, hidden)
    if patterns and _is_excluded(root, root.parent, patterns):
        return []
    return [root]


def _collect_recursive(root: Path, current: Path, patterns: list[str], hidden: bool) -> list[Path]:
    candidates: list[Path] = []
    with os.scandir(current) as entries:
        for entry in entries:
            child = Path(entry.path)
            if not hidden and entry.name.startswith("."):
                continue
            if patterns and _is_excluded(child, root, patterns):
                continue
            if entry.is_dir(follow_symlinks=False):
                candidates.extend(_collect_recursive(root, child, patterns, hidden))
                candidates.append(child)
            else:
                candidates.append(child)
    return candidates


def _is_excluded(path: Path, root: Path, patterns: list[str]) -> bool:
    absolute = str(path)
    basename = path.name
    try:
        relative = path.relative_to(root)
    except ValueError:
        relative = Path(path.name)
    relative_forms = {str(relative), relative.as_posix()}
    candidates = {absolute, basename, *relative_forms}
    return any(fnmatch.fnmatch(candidate, pattern) for candidate in candidates for pattern in patterns)


def _parse_sort(sort: str) -> _SortSpec:
    text = sort.strip()
    if not text:
        raise ValueError("sort cannot be empty")
    direction = "<"
    if text[0] in "<>":
        direction = text[0]
        text = text[1:]
    field = text.lower()
    if field not in {"name", "size", "ext"}:
        raise ValueError("sort must be NAME, SIZE, or ext with optional < or > prefix")
    return _SortSpec(field=field, reverse=direction == ">")


def _sort_key(path: Path, sort_spec: _SortSpec) -> tuple[int | str, str]:
    if sort_spec.field == "name":
        return (path.stem.casefold(), path.name.casefold())
    if sort_spec.field == "size":
        return (path.stat().st_size, path.name.casefold())
    return (path.suffix.casefold().lstrip("."), path.name.casefold())


def _template_has_counter(template: str) -> bool:
    for field in _template_fields(template):
        if COUNTER_PATTERN.fullmatch(field.strip()):
            return True
    return False


def _template_fields(template: str) -> list[str]:
    fields: list[str] = []
    index = 0
    while index < len(template):
        char = template[index]
        if char == "{" and index + 1 < len(template) and template[index + 1] == "{":
            index += 2
            continue
        if char == "}" and index + 1 < len(template) and template[index + 1] == "}":
            index += 2
            continue
        if char == "{":
            end = template.find("}", index + 1)
            if end == -1:
                raise ValueError("template has an unmatched '{'")
            fields.append(template[index + 1 : end])
            index = end + 1
            continue
        if char == "}":
            raise ValueError("template has an unmatched '}'")
        index += 1
    return fields


def _render_new_basename(source: Path, template: str, index: int) -> str:
    original_name = source.name if source.is_dir() else source.stem
    rendered = _render_template(template, original_name, index)
    _validate_rendered_name(rendered)
    if source.is_file() and not Path(rendered).suffix:
        rendered = f"{rendered}{source.suffix}"
    _validate_rendered_name(rendered)
    return rendered


def _render_template(template: str, name: str, index: int) -> str:
    result: list[str] = []
    evaluator = _NameExpressionEvaluator(name)
    position = 0

    while position < len(template):
        char = template[position]
        if char == "{" and position + 1 < len(template) and template[position + 1] == "{":
            result.append("{")
            position += 2
            continue
        if char == "}" and position + 1 < len(template) and template[position + 1] == "}":
            result.append("}")
            position += 2
            continue
        if char == "{":
            end = template.find("}", position + 1)
            if end == -1:
                raise ValueError("template has an unmatched '{'")
            field = template[position + 1 : end].strip()
            if not field:
                raise ValueError("template has an empty placeholder")
            result.append(_render_field(field, evaluator, index))
            position = end + 1
            continue
        if char == "}":
            raise ValueError("template has an unmatched '}'")
        result.append(char)
        position += 1

    return "".join(result)


def _render_field(field: str, evaluator: _NameExpressionEvaluator, index: int) -> str:
    counter_match = COUNTER_PATTERN.fullmatch(field)
    if counter_match:
        direction, digits = counter_match.groups()
        start = int(digits)
        value = start - index if direction == ">" else start + index
        return str(value).zfill(len(digits))
    return str(evaluator.evaluate(field))


def _validate_rendered_name(name: str) -> None:
    if not name or name in {".", ".."}:
        raise ValueError("rendered name cannot be empty, '.', or '..'")
    if "\x00" in name:
        raise ValueError("rendered name cannot contain a null byte")
    if any(separator in name for separator in ("/", "\\")):
        raise ValueError("rendered name cannot contain path separators")


def _validate_plan(changing_plans: list[RenamePlan], all_plans: list[RenamePlan]) -> None:
    target_keys: dict[str, Path] = {}
    for plan in changing_plans:
        key = _normcase(plan.target)
        previous = target_keys.get(key)
        if previous is not None:
            raise ValueError(f"multiple sources would rename to the same target: {plan.target}")
        target_keys[key] = plan.target

    moving_sources = {_normcase(plan.source) for plan in changing_plans}
    for plan in changing_plans:
        if plan.target.exists() and _normcase(plan.target) not in moving_sources:
            raise ValueError(f"target already exists: {plan.target}")

    all_targets = {plan.source: plan.target for plan in all_plans}
    target_set = {_normcase(plan.target) for plan in changing_plans}

    def final_path_for(path: Path) -> Path:
        current = path.parent
        while True:
            target = all_targets.get(current)
            if target is not None:
                return target / path.relative_to(current)
            if current == current.parent:
                return path
            current = current.parent

    for plan in all_plans:
        if not plan.source.is_dir():
            continue
        for current, dirs, files in os.walk(plan.source):
            for name in [*dirs, *files]:
                existing = Path(current) / name
                if _normcase(existing) in moving_sources:
                    continue
                if _normcase(final_path_for(existing)) in target_set:
                    raise ValueError(f"target would conflict with existing path: {final_path_for(existing)}")


def _normcase(path: Path) -> str:
    return os.path.normcase(os.fspath(path))


def _path_depth(path: Path) -> int:
    return len(path.parts)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bename",
        description="Safely rename files and directories with templates. Use 'bn' as a short shell alias.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  bename image.png -n 'photo_{NAME}'\n"
            "  bename . -n '{<001}-{NAME}' -r -s '<size'\n"
            "  bn . -n '{<001}{NAME}' -s '<SIZE'\n"
            "\n"
            "placeholders:\n"
            "  {NAME}       original stem for files, full name for directories\n"
            "  {<001}       ascending counter starting at 001\n"
            "  {>512}       descending counter starting at 512\n"
            "  {NAME.lower()} and {NAME.split('_')[0]} are safe NAME expressions"
        ),
    )
    parser.add_argument("path", nargs="?", type=Path, help="file or directory to rename")
    parser.add_argument("-n", "--new-name", metavar="RENAME", help="rename template")
    parser.add_argument(
        "-e",
        "--exclude",
        nargs="+",
        default=[],
        metavar="PATH",
        help="exclude fnmatch patterns, matched against path, relative path, and basename",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="rename directory contents recursively instead of the directory itself",
    )
    parser.add_argument(
        "--hidden",
        action="store_true",
        help="include hidden files and directories during recursive renames",
    )
    parser.add_argument(
        "-s",
        "--sort",
        metavar="SORT",
        help="counter assignment sort: NAME, SIZE, ext with optional < or > prefix",
    )
    parser.add_argument(
        "--self-test",
        "--tests",
        action="store_true",
        help="run built-in self-tests and exit",
    )
    return parser


def _main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.self_test:
        return 0 if _run_tests() else 1
    if args.path is None:
        parser.error("PATH is required unless --self-test is used")
    if not args.new_name:
        parser.error("-n/--new-name is required unless --self-test is used")

    try:
        results = rename_paths(
            args.path,
            args.new_name,
            exclude=args.exclude,
            recursive=args.recursive,
            hidden=args.hidden,
            sort=args.sort,
        )
    except (FileNotFoundError, OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    if not results:
        print("No matching paths to rename.")
        return 0

    for result in results:
        print(f"{result.source} -> {result.target}")
    return 0


def _run_tests() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = root / "image.png"
        source.write_text("x", encoding="utf-8")
        results = rename_paths(source, "photo_{NAME}")
        assert len(results) == 1
        assert (root / "photo_image.png").read_text(encoding="utf-8") == "x"

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "b.txt").write_text("bb", encoding="utf-8")
        (root / "a.txt").write_text("a", encoding="utf-8")
        results = rename_paths(root, "{<001}-{NAME}.md", recursive=True, sort="<NAME")
        assert [result.target.name for result in results] == ["001-a.md", "002-b.md"]
        assert (root / "001-a.md").exists()
        assert (root / "002-b.md").exists()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "small.bin").write_bytes(b"1")
        (root / "large.bin").write_bytes(b"12345")
        rename_paths(root, "{>09}-{NAME}", recursive=True, sort=">size")
        assert (root / "09-large.bin").exists()
        assert (root / "08-small.bin").exists()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "keep.tmp").write_text("keep", encoding="utf-8")
        (root / ".secret").write_text("hidden", encoding="utf-8")
        (root / "change.txt").write_text("change", encoding="utf-8")
        rename_paths(root, "x-{NAME}", exclude=["*.tmp"], recursive=True)
        assert (root / "keep.tmp").exists()
        assert (root / ".secret").exists()
        assert (root / "x-change.txt").exists()

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        subdir = root / "sub"
        subdir.mkdir()
        (subdir / "file.txt").write_text("nested", encoding="utf-8")
        results = rename_paths(root, "{<01}-{NAME}", recursive=True, sort="<name")
        assert [result.target.name for result in results] == ["01-file.txt", "02-sub"]
        assert (root / "02-sub" / "01-file.txt").read_text(encoding="utf-8") == "nested"

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "a.txt").write_text("a", encoding="utf-8")
        (root / "b.txt").write_text("b", encoding="utf-8")
        try:
            rename_paths(root / "a.txt", "b")
        except ValueError as error:
            assert "target already exists" in str(error)
        else:
            raise AssertionError("expected target conflict")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        subdir = root / "sub"
        subdir.mkdir()
        (subdir / "a.txt").write_text("a", encoding="utf-8")
        (subdir / "b.txt").write_text("b", encoding="utf-8")
        try:
            rename_paths(root, "b", exclude=["b.txt"], recursive=True)
        except ValueError as error:
            assert "target would conflict" in str(error)
        else:
            raise AssertionError("expected carried descendant conflict")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "hello_world.txt").write_text("x", encoding="utf-8")
        rename_paths(root / "hello_world.txt", "{NAME.split('_')[0].upper()}")
        assert (root / "HELLO.txt").exists()
        assert render_name("one two", "{NAME.split[1]}") == "two"

    print("bename self-tests passed")
    return True


if __name__ == "__main__":
    raise SystemExit(_main())
