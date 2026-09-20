# CODEPILLS-META-BEGIN
# schema: codepills.tool/v1
# name: dirinit
# version: 1.1.0
# author: octanima-labs
# description: Create directory and file structures from an indented text specification with optional templates.
# repo: https://github.com/octanima-labs/codepills/blob/main/python/dirinit.py
# license: MIT
# usage: python python/dirinit.py PATH [--root-dir PATH] [--force] [--vars "KEY=VALUE ..."]
# tags:
#   - python
#   - cli
#   - filesystem
#   - scaffold
# requires:
#   - Python standard library
# platforms:
#   - Linux
#   - macOS
#   - Windows
# CODEPILLS-META-END

"""Create directory and file structures from a text specification.

``dirinit`` accepts a plain text file that describes directories and files using
two-space indentation, slash-separated paths, or a mix of both. Directory entries
must end with ``/``. After the hierarchy, optional ``--- PATH`` template sections
can define file contents. Templates may use dotted placeholders such as
``{{ project.name }}``, supplied through the CLI or API as nested variables.
"""

from __future__ import annotations

import argparse
import fnmatch
import io
import os
import re
import shlex
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO


TEMPLATE_FILE_CONTENT = "TEMPLATE FILE"
INDENT_WIDTH = 2
TEMPLATE_HEADER_RE = re.compile(r"^---\s+(.+?)\s*$")
VARIABLE_RE = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\s*}}")


@dataclass(frozen=True)
class StructureEntry:
    """One explicit entry parsed from a dirinit specification file."""

    line_number: int
    raw: str
    relative_path: Path
    is_dir: bool


@dataclass(frozen=True)
class CreatedEntry:
    """One path considered during structure creation."""

    target: Path
    is_dir: bool
    created: bool
    skipped: bool
    explicit: bool


@dataclass(frozen=True)
class _FileTemplate:
    selector: str
    content: str
    line_number: int


@dataclass(frozen=True)
class _ParsedSpec:
    entries: list[StructureEntry]
    templates: list[_FileTemplate]


@dataclass(frozen=True)
class _Operation:
    relative_path: Path
    is_dir: bool
    explicit: bool
    line_number: int


def parse_structure_file(path: str | os.PathLike[str]) -> list[StructureEntry]:
    """Parse a structure file into normalized relative entries.

    Blank lines and lines whose first non-space character is ``#`` are ignored.
    Indentation must use exactly two spaces per level. A leading ``/`` is a
    structure-root marker, not a filesystem absolute path.
    """

    return _parse_spec_file(path).entries


def _parse_spec_file(path: str | os.PathLike[str]) -> _ParsedSpec:
    spec_path = _absolute_path(path)
    hierarchy_lines, templates = _split_spec_sections(spec_path)

    entries = _parse_structure_lines(hierarchy_lines)
    _validate_templates(templates)
    return _ParsedSpec(entries=entries, templates=templates)


def _split_spec_sections(spec_path: Path) -> tuple[list[tuple[int, str]], list[_FileTemplate]]:
    hierarchy_lines: list[tuple[int, str]] = []
    templates: list[_FileTemplate] = []
    current_selector: str | None = None
    current_line_number = 0
    current_content: list[str] = []

    def finish_template() -> None:
        nonlocal current_selector, current_line_number, current_content
        if current_selector is not None:
            templates.append(
                _FileTemplate(
                    selector=current_selector,
                    content="".join(current_content).rstrip("\n\r"),
                    line_number=current_line_number,
                )
            )
        current_selector = None
        current_line_number = 0
        current_content = []

    with spec_path.open("r", encoding="utf-8") as handle:
        for line_number, raw_line in enumerate(handle, start=1):
            line = raw_line.rstrip("\n\r")
            header_match = TEMPLATE_HEADER_RE.match(line)
            if header_match:
                finish_template()
                current_selector = header_match.group(1)
                current_line_number = line_number
                current_content = []
                continue
            if current_selector is None and line == "---":
                raise ValueError(f"line {line_number}: template header requires a selector path")
            if current_selector is None:
                hierarchy_lines.append((line_number, raw_line))
            else:
                current_content.append(raw_line)

    finish_template()
    return hierarchy_lines, templates


def _parse_structure_lines(lines: list[tuple[int, str]]) -> list[StructureEntry]:
    entries: list[StructureEntry] = []
    directory_stack: dict[int, tuple[str, ...]] = {}

    for line_number, raw_line in lines:
        line = raw_line.rstrip("\n\r").rstrip()
        if not line.strip() or line.lstrip(" ").startswith("#"):
            continue
        if "\t" in line:
            raise ValueError(f"line {line_number}: indentation must use spaces, not tabs")

        indent_spaces = len(line) - len(line.lstrip(" "))
        if indent_spaces % INDENT_WIDTH:
            raise ValueError(f"line {line_number}: indentation must use multiples of two spaces")
        depth = indent_spaces // INDENT_WIDTH
        text = line[indent_spaces:]

        parts, is_dir, rooted = _parse_entry_text(text, line_number)
        if rooted:
            relative_parts = parts
        else:
            if depth == 0:
                parent_parts: tuple[str, ...] = ()
            else:
                parent_parts = directory_stack.get(depth - 1, ())
                if not parent_parts:
                    raise ValueError(f"line {line_number}: indented entry has no parent directory")
            relative_parts = (*parent_parts, *parts)

        for stale_depth in [stack_depth for stack_depth in directory_stack if stack_depth >= depth]:
            del directory_stack[stale_depth]

        if is_dir:
            directory_stack[depth] = relative_parts

        entries.append(
            StructureEntry(
                line_number=line_number,
                raw=text,
                relative_path=Path(*relative_parts),
                is_dir=is_dir,
            )
        )

    _validate_entries(entries)
    return entries


def preview_structure(
    path: str | os.PathLike[str], root_dir: str | os.PathLike[str] | None = None
) -> list[StructureEntry]:
    """Parse and preflight a structure file without creating anything."""

    entries = parse_structure_file(path)
    base_dir = _base_dir(path, root_dir)
    operations = _build_operations(entries)
    _preflight_operations(operations, base_dir, force=False)
    return entries


def create_structure(
    path: str | os.PathLike[str],
    root_dir: str | os.PathLike[str] | None = None,
    force: bool = False,
    variables: dict[str, object] | None = None,
    warning_stream: TextIO | None = sys.stderr,
) -> list[CreatedEntry]:
    """Create a directory and file structure from ``path``.

    Args:
        path: Text specification file.
        root_dir: Optional creation base. Defaults to the spec file's parent.
        force: Skip existing paths instead of failing, after validating the full
            plan for malformed paths and type conflicts.
        variables: Optional nested dictionary for ``{{ dotted.key }}`` template
            placeholders.
    """

    parsed = _parse_spec_file(path)
    entries = parsed.entries
    base_dir = _base_dir(path, root_dir)
    operations = _build_operations(entries)
    _preflight_operations(operations, base_dir, force=force)
    template_root = _template_root(entries)
    missing_variables: set[str] = set()

    if base_dir.exists() and not base_dir.is_dir():
        raise ValueError(f"root directory is not a directory: {base_dir}")
    base_dir.mkdir(parents=True, exist_ok=True)

    results: list[CreatedEntry] = []
    for operation in _creation_order(operations):
        target = base_dir / operation.relative_path
        if target.exists():
            results.append(
                CreatedEntry(
                    target=target,
                    is_dir=operation.is_dir,
                    created=False,
                    skipped=True,
                    explicit=operation.explicit,
                )
            )
            continue

        if operation.is_dir:
            target.mkdir()
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            content = _content_for_file(operation.relative_path, template_root, parsed.templates, variables or {}, missing_variables)
            target.write_text(content, encoding="utf-8")

        results.append(
            CreatedEntry(
                target=target,
                is_dir=operation.is_dir,
                created=True,
                skipped=False,
                explicit=operation.explicit,
            )
        )

    if warning_stream is not None:
        for variable_name in sorted(missing_variables):
            print(f"var {variable_name} not provided", file=warning_stream)

    return results


def _absolute_path(path: str | os.PathLike[str]) -> Path:
    return Path(os.path.abspath(os.path.expanduser(os.fspath(path))))


def _base_dir(path: str | os.PathLike[str], root_dir: str | os.PathLike[str] | None) -> Path:
    if root_dir is not None:
        return _absolute_path(root_dir)
    return _absolute_path(path).parent


def _parse_entry_text(text: str, line_number: int) -> tuple[tuple[str, ...], bool, bool]:
    if not text:
        raise ValueError(f"line {line_number}: empty path entry")
    if "\\" in text:
        raise ValueError(f"line {line_number}: use '/' path separators, not backslashes")
    if re.match(r"^[A-Za-z]:", text):
        raise ValueError(f"line {line_number}: Windows drive paths are not allowed")

    rooted = text.startswith("/")
    body = text[1:] if rooted else text
    is_dir = body.endswith("/")
    if is_dir:
        body = body[:-1]
    if not body:
        raise ValueError(f"line {line_number}: empty path entry")

    parts = tuple(body.split("/"))
    if any(part == "" for part in parts):
        raise ValueError(f"line {line_number}: empty path components are not allowed")

    for part in parts:
        if part in {".", ".."}:
            raise ValueError(f"line {line_number}: unsafe path component: {part}")
        if "\x00" in part:
            raise ValueError(f"line {line_number}: null bytes are not allowed")
        if ":" in part:
            raise ValueError(f"line {line_number}: drive-like path components are not allowed")

    return parts, is_dir, rooted


def _validate_templates(templates: list[_FileTemplate]) -> None:
    seen: dict[str, _FileTemplate] = {}
    for template in templates:
        selector = template.selector
        if selector == "---" or not selector.strip():
            raise ValueError(f"line {template.line_number}: template header requires a selector path")
        if selector.startswith("/"):
            raise ValueError(f"line {template.line_number}: template selector must be relative: {selector}")
        if selector.endswith("/"):
            raise ValueError(f"line {template.line_number}: template selector must target a file: {selector}")
        if "\\" in selector:
            raise ValueError(f"line {template.line_number}: use '/' path separators in template selectors")
        if re.match(r"^[A-Za-z]:", selector):
            raise ValueError(f"line {template.line_number}: Windows drive paths are not allowed in template selectors")

        parts = selector.split("/")
        if any(part == "" for part in parts):
            raise ValueError(f"line {template.line_number}: empty selector components are not allowed")
        for part in parts:
            if part in {".", ".."}:
                raise ValueError(f"line {template.line_number}: unsafe template selector component: {part}")
            if "\x00" in part:
                raise ValueError(f"line {template.line_number}: null bytes are not allowed in template selectors")
            if ":" in part:
                raise ValueError(f"line {template.line_number}: drive-like selector components are not allowed")

        key = selector.casefold()
        previous = seen.get(key)
        if previous is not None:
            raise ValueError(
                f"line {template.line_number}: duplicate template selector also declared on line "
                f"{previous.line_number}: {selector}"
            )
        seen[key] = template


def _template_root(entries: list[StructureEntry]) -> tuple[str, ...]:
    top_level = {entry.relative_path.parts[0] for entry in entries if entry.relative_path.parts}
    if len(top_level) != 1:
        return ()
    root = next(iter(top_level))
    if any(entry.relative_path == Path(root) and entry.is_dir for entry in entries):
        return (root,)
    return ()


def _content_for_file(
    relative_path: Path,
    template_root: tuple[str, ...],
    templates: list[_FileTemplate],
    variables: dict[str, object],
    missing_variables: set[str],
) -> str:
    template = _select_template(relative_path, template_root, templates)
    if template is None:
        return TEMPLATE_FILE_CONTENT
    return _render_template(template.content, variables, missing_variables)


def _select_template(relative_path: Path, template_root: tuple[str, ...], templates: list[_FileTemplate]) -> _FileTemplate | None:
    if not templates:
        return None

    match_path = _template_match_path(relative_path, template_root)
    matches = [template for template in templates if fnmatch.fnmatchcase(match_path, template.selector)]
    if not matches:
        return None
    return max(matches, key=lambda template: _selector_specificity(template.selector))


def _template_match_path(relative_path: Path, template_root: tuple[str, ...]) -> str:
    parts = relative_path.parts
    if template_root and parts[: len(template_root)] == template_root and len(parts) > len(template_root):
        parts = parts[len(template_root) :]
    return Path(*parts).as_posix()


def _selector_specificity(selector: str) -> tuple[int, int, int]:
    wildcard_count = selector.count("*") + selector.count("?") + selector.count("[")
    return (0 if wildcard_count else 1, -wildcard_count, len(selector.replace("*", "").replace("?", "")))


def _render_template(content: str, variables: dict[str, object], missing_variables: set[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        variable_name = match.group(1)
        value = _resolve_variable(variable_name, variables)
        if value is None:
            missing_variables.add(variable_name)
            return ""
        return str(value)

    return VARIABLE_RE.sub(replace, content)


def _resolve_variable(variable_name: str, variables: dict[str, object]) -> object | None:
    current: object = variables
    for part in variable_name.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _parse_vars(raw_vars: str | None) -> dict[str, object]:
    parsed: dict[str, object] = {}
    if not raw_vars:
        return parsed

    for token in shlex.split(raw_vars):
        if "=" not in token:
            raise ValueError(f"variable assignment must use KEY=VALUE: {token}")
        key, value = token.split("=", 1)
        _assign_variable(parsed, key, value)
    return parsed


def _assign_variable(variables: dict[str, object], key: str, value: str) -> None:
    parts = key.split(".")
    if any(part == "" for part in parts):
        raise ValueError(f"variable key contains an empty path segment: {key}")

    current = variables
    for part in parts[:-1]:
        existing = current.get(part)
        if existing is None:
            nested: dict[str, object] = {}
            current[part] = nested
            current = nested
            continue
        if not isinstance(existing, dict):
            raise ValueError(f"variable assignment conflicts with scalar path: {key}")
        current = existing

    leaf = parts[-1]
    existing_leaf = current.get(leaf)
    if isinstance(existing_leaf, dict):
        raise ValueError(f"variable assignment conflicts with nested path: {key}")
    current[leaf] = value


def _validate_entries(entries: list[StructureEntry]) -> None:
    seen_explicit: dict[str, StructureEntry] = {}
    explicit_files: dict[str, StructureEntry] = {}

    for entry in entries:
        key = _relative_key(entry.relative_path)
        previous = seen_explicit.get(key)
        if previous is not None:
            raise ValueError(
                f"line {entry.line_number}: duplicate target path also declared on line "
                f"{previous.line_number}: {entry.relative_path.as_posix()}"
            )
        seen_explicit[key] = entry

        for parent in _relative_parents(entry.relative_path):
            parent_key = _relative_key(parent)
            file_entry = explicit_files.get(parent_key)
            if file_entry is not None:
                raise ValueError(
                    f"line {entry.line_number}: path is nested under file declared on line "
                    f"{file_entry.line_number}: {parent.as_posix()}"
                )

        if not entry.is_dir:
            explicit_files[key] = entry


def _build_operations(entries: list[StructureEntry]) -> list[_Operation]:
    operations: dict[str, _Operation] = {}

    def add_operation(relative_path: Path, is_dir: bool, explicit: bool, line_number: int) -> None:
        key = _relative_key(relative_path)
        existing = operations.get(key)
        if existing is not None:
            if existing.is_dir != is_dir:
                raise ValueError(f"line {line_number}: path is both a file and a directory: {relative_path.as_posix()}")
            if explicit and not existing.explicit:
                operations[key] = _Operation(relative_path=relative_path, is_dir=is_dir, explicit=True, line_number=line_number)
            return
        operations[key] = _Operation(relative_path=relative_path, is_dir=is_dir, explicit=explicit, line_number=line_number)

    for entry in entries:
        for parent in _relative_parents(entry.relative_path):
            add_operation(parent, is_dir=True, explicit=False, line_number=entry.line_number)
        add_operation(entry.relative_path, entry.is_dir, explicit=True, line_number=entry.line_number)

    return list(operations.values())


def _preflight_operations(operations: list[_Operation], base_dir: Path, force: bool) -> None:
    if base_dir.exists() and not base_dir.is_dir():
        raise ValueError(f"root directory is not a directory: {base_dir}")

    for operation in operations:
        target = base_dir / operation.relative_path
        if not _is_within_base(base_dir, target):
            raise ValueError(f"line {operation.line_number}: target escapes root directory: {operation.relative_path}")

        if not target.exists():
            continue

        if operation.is_dir and not target.is_dir():
            raise ValueError(f"target exists but is not a directory: {target}")
        if not operation.is_dir and not target.is_file():
            raise ValueError(f"target exists but is not a file: {target}")
        if not force:
            kind = "directory" if operation.is_dir else "file"
            raise FileExistsError(f"{kind} already exists: {target}")


def _creation_order(operations: list[_Operation]) -> list[_Operation]:
    return sorted(operations, key=lambda item: (not item.is_dir, len(item.relative_path.parts), item.relative_path.as_posix()))


def _relative_parents(path: Path) -> list[Path]:
    parts = path.parts
    return [Path(*parts[:index]) for index in range(1, len(parts))]


def _relative_key(path: Path) -> str:
    return path.as_posix().casefold()


def _is_within_base(base_dir: Path, target: Path) -> bool:
    try:
        target.resolve(strict=False).relative_to(base_dir.resolve(strict=False))
    except ValueError:
        return False
    return True


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dirinit",
        description="Create directories and files from a text structure file with optional templates.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  dirinit structure.txt\n"
            "  dirinit structure.txt --root-dir /tmp/project\n"
            "  dirinit structure.txt --force\n"
            "  dirinit structure.txt --vars \"project.name=Demo description='Hello world'\"\n"
            "\n"
            "syntax:\n"
            "  root/              # directories end with /\n"
            "    file.txt         # files do not end with /\n"
            "  /root/dir/file.txt # leading / is a spec-root marker\n"
            "\n"
            "templates:\n"
            "  --- */README.md   # template headers require a selector\n"
            "  # {{ project.name }}"
        ),
    )
    parser.add_argument("path", nargs="?", type=Path, help="text structure file")
    parser.add_argument(
        "-r",
        "--root-dir",
        type=Path,
        help="creation base directory; defaults to the structure file's parent",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="skip existing paths and create missing paths after preflight validation",
    )
    parser.add_argument(
        "--vars",
        metavar="ASSIGNMENTS",
        help="template variables as shell-style KEY=VALUE tokens; dotted keys create nested values",
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

    try:
        variables = _parse_vars(args.vars)
        results = create_structure(args.path, root_dir=args.root_dir, force=args.force, variables=variables)
    except (FileNotFoundError, FileExistsError, OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    for result in results:
        action = "skipped" if result.skipped else "created"
        suffix = "/" if result.is_dir else ""
        print(f"{action}: {result.target}{suffix}")
    return 0


def _write_spec(path: Path, content: str) -> None:
    path.write_text(content.strip("\n") + "\n", encoding="utf-8")


def _run_tests() -> bool:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        spec = base / "tree.txt"
        _write_spec(
            spec,
            """
root/
  dir-1/
    sdir-1/
      ssdir-1/
        file1
    sdir-2/
    sdir-3/
      file2.txt
      file3.png
  dir-2/
  dir-3/
""",
        )
        create_structure(spec)
        assert (base / "root" / "dir-1" / "sdir-1" / "ssdir-1" / "file1").read_text(encoding="utf-8") == TEMPLATE_FILE_CONTENT
        assert (base / "root" / "dir-1" / "sdir-2").is_dir()
        assert (base / "root" / "dir-1" / "sdir-3" / "file3.png").is_file()

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        spec = base / "absolute-like.txt"
        _write_spec(
            spec,
            """
/root/
/root/dir-1/
/root/dir-1/sdir-1/
/root/dir-1/sdir-1/ssdir-1/file1
/root/dir-1/sdir-3/file2.txt
/root/dir-2/
""",
        )
        entries = preview_structure(spec)
        assert entries[0].relative_path == Path("root")
        create_structure(spec)
        assert (base / "root" / "dir-1" / "sdir-1" / "ssdir-1" / "file1").exists()

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        spec = base / "mixed.txt"
        _write_spec(
            spec,
            """
/root/dir-1/sdir-1/
  ssdir-1/file1
  ssdir-2/
  ssdir-3/
    file2.txt
    file3.png
/root/dir-2/
""",
        )
        create_structure(spec)
        assert (base / "root" / "dir-1" / "sdir-1" / "ssdir-1" / "file1").exists()
        assert (base / "root" / "dir-1" / "sdir-1" / "ssdir-3" / "file2.txt").exists()

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        root_dir = base / "custom-root"
        spec = base / "tree.txt"
        _write_spec(spec, "root/\n  file.txt\n")
        create_structure(spec, root_dir=root_dir)
        assert (root_dir / "root" / "file.txt").read_text(encoding="utf-8") == TEMPLATE_FILE_CONTENT

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        spec = base / "force.txt"
        _write_spec(spec, "root/\n  file.txt\n  new.txt\n")
        (base / "root").mkdir()
        (base / "root" / "file.txt").write_text("existing", encoding="utf-8")
        try:
            create_structure(spec)
        except FileExistsError as error:
            assert "already exists" in str(error)
        else:
            raise AssertionError("expected existing path error")
        results = create_structure(spec, force=True)
        assert (base / "root" / "file.txt").read_text(encoding="utf-8") == "existing"
        assert (base / "root" / "new.txt").read_text(encoding="utf-8") == TEMPLATE_FILE_CONTENT
        assert any(result.skipped for result in results)

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        spec = base / "duplicate.txt"
        _write_spec(spec, "root/\nroot/\n")
        try:
            parse_structure_file(spec)
        except ValueError as error:
            assert "duplicate target" in str(error)
        else:
            raise AssertionError("expected duplicate target error")

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        for filename, content in {
            "traversal.txt": "root/../x\n",
            "drive.txt": "C:/x\n",
            "empty.txt": "root//x\n",
            "indent.txt": "  orphan\n",
        }.items():
            spec = base / filename
            _write_spec(spec, content)
            try:
                parse_structure_file(spec)
            except ValueError:
                pass
            else:
                raise AssertionError(f"expected unsafe spec error for {filename}")

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        spec = base / "templates.txt"
        _write_spec(
            spec,
            """
root/
  cat/
    README.md
    file.txt
    exact.txt
    missing.txt
    plain.bin
  cat2/
    README.md
    file.txt
  README.md

--- */file.txt
Some text {{ var.subvar.name }} blabla

--- */README.md
# {{ category_name }}

{{ category_description }}

---

--- README.md
# {{ root }}

{{ description }}

--- cat/exact.txt
Exact wins

--- */exact.txt
Wildcard loses

--- */missing.txt
{{ missing.value }}
""",
        )
        warnings = io.StringIO()
        create_structure(
            spec,
            variables={
                "var": {"subvar": {"name": "Name"}},
                "category_name": "Category",
                "category_description": "Description",
                "root": "Root",
                "description": "Root description",
            },
            warning_stream=warnings,
        )
        assert (base / "root" / "cat" / "file.txt").read_text(encoding="utf-8") == "Some text Name blabla"
        assert (base / "root" / "cat2" / "file.txt").read_text(encoding="utf-8") == "Some text Name blabla"
        assert (base / "root" / "README.md").read_text(encoding="utf-8") == "# Root\n\nRoot description"
        assert (base / "root" / "cat" / "README.md").read_text(encoding="utf-8") == "# Category\n\nDescription\n\n---"
        assert (base / "root" / "cat" / "exact.txt").read_text(encoding="utf-8") == "Exact wins"
        assert (base / "root" / "cat" / "missing.txt").read_text(encoding="utf-8") == ""
        assert (base / "root" / "cat" / "plain.bin").read_text(encoding="utf-8") == TEMPLATE_FILE_CONTENT
        assert warnings.getvalue() == "var missing.value not provided\n"
        entries = parse_structure_file(spec)
        assert all(entry.raw != "--- */file.txt" for entry in entries)

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        spec = base / "multi-root.txt"
        _write_spec(
            spec,
            """
root1/
  README.md
root2/
  README.md

--- README.md
Base README

--- root1/README.md
Root 1 README
""",
        )
        create_structure(spec)
        assert (base / "root1" / "README.md").read_text(encoding="utf-8") == "Root 1 README"
        assert (base / "root2" / "README.md").read_text(encoding="utf-8") == TEMPLATE_FILE_CONTENT

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        for filename, (content, expected) in {
            "empty-template.txt": ("root/\n  file.txt\n\n---\n", "template header requires a selector path"),
            "duplicate-template.txt": ("root/\n  file.txt\n\n--- file.txt\none\n--- file.txt\ntwo\n", "duplicate template selector"),
        }.items():
            spec = base / filename
            _write_spec(spec, content)
            try:
                create_structure(spec)
            except ValueError as error:
                assert expected in str(error)
            else:
                raise AssertionError(f"expected template error for {filename}")

    assert _parse_vars("category.name=Docs root=Project") == {"category": {"name": "Docs"}, "root": "Project"}
    assert _parse_vars("description='Hello world'") == {"description": "Hello world"}
    for raw_vars in ("a=1 a.b=2", "a.b=2 a=1"):
        try:
            _parse_vars(raw_vars)
        except ValueError as error:
            assert "conflicts" in str(error)
        else:
            raise AssertionError(f"expected variable conflict for {raw_vars}")

    print("dirinit self-tests passed")
    return True


if __name__ == "__main__":
    raise SystemExit(_main())
