# CODEPILLS-META-BEGIN
# schema: codepills.tool/v1
# name: beautify
# version: 1.0.0
# author: octanima-labs
# description: Beautify JSON, XML, and HTML files in place.
# repo: https://github.com/octanima-labs/codepills/blob/main/python/beautify.py
# license: MIT
# usage: python python/beautify.py PATH [OPTIONS]
# tags:
#   - python
#   - cli
#   - formatter
# requires:
#   - Python standard library
# platforms:
#   - Linux
#   - macOS
#   - Windows
# CODEPILLS-META-END

"""Beautify JSON, XML, and HTML from a CLI or importable module.

Beautify rewrites supported files in place. Syntax detection is intentionally
extension-only: ``.json`` files are parsed as JSON, ``.xml`` files as XML, and
``.html`` or ``.htm`` files as HTML. Unknown extensions are not content-sniffed.
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import tempfile
import xml.dom.minidom
from contextlib import redirect_stderr, redirect_stdout
from html import escape
from html.parser import HTMLParser
from pathlib import Path


SUPPORTED_SYNTAXES = {
    ".json": "json",
    ".xml": "xml",
    ".html": "html",
    ".htm": "html",
}

__all__ = [
    "SUPPORTED_SYNTAXES",
    "BeautifyError",
    "beautify_json",
    "beautify_xml",
    "beautify_html",
    "detect_syntax",
    "beautify_file",
    "beautify_paths",
]


class BeautifyError(ValueError):
    """Raised when a target cannot be beautified."""


class _HTMLBeautifier(HTMLParser):
    """Small HTML formatter for valid HTML fragments and documents."""

    def __init__(self, indent: str):
        super().__init__(convert_charrefs=False)
        self.indent = indent
        self.depth = 0
        self.lines: list[str] = []
        self.void_tags = {
            "area",
            "base",
            "br",
            "col",
            "embed",
            "hr",
            "img",
            "input",
            "link",
            "meta",
            "param",
            "source",
            "track",
            "wbr",
        }

    def handle_decl(self, decl: str) -> None:
        self.lines.append(f"{self.indent * self.depth}<!{decl}>")

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.lines.append(f"{self.indent * self.depth}<{tag}{self._attrs(attrs)}>")
        if tag.lower() not in self.void_tags:
            self.depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.lines.append(f"{self.indent * self.depth}<{tag}{self._attrs(attrs)} />")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() not in self.void_tags:
            self.depth = max(0, self.depth - 1)
        self.lines.append(f"{self.indent * self.depth}</{tag}>")

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.lines.append(f"{self.indent * self.depth}{text}")

    def handle_entityref(self, name: str) -> None:
        self.lines.append(f"{self.indent * self.depth}&{name};")

    def handle_charref(self, name: str) -> None:
        self.lines.append(f"{self.indent * self.depth}&#{name};")

    def handle_comment(self, data: str) -> None:
        self.lines.append(f"{self.indent * self.depth}<!--{data}-->")

    @staticmethod
    def _attrs(attrs: list[tuple[str, str | None]]) -> str:
        parts = []
        for key, value in attrs:
            if value is None:
                parts.append(f" {key}")
            else:
                parts.append(f' {key}="{escape(value, quote=True)}"')
        return "".join(parts)


def _indent_string(indent: int) -> str:
    if indent < 0:
        raise BeautifyError("indent must be zero or greater")
    return " " * indent


def beautify_json(json_text: str, indent: int = 4) -> str:
    """Return pretty-printed JSON text."""

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as error:
        raise BeautifyError(f"invalid JSON: {error}") from error
    return json.dumps(data, indent=indent, ensure_ascii=False)


def beautify_xml(xml_text: str, indent: int = 4) -> str:
    """Return pretty-printed XML text."""

    try:
        compact = re.sub(r">\s+<", "><", xml_text.strip())
        dom = xml.dom.minidom.parseString(compact)
    except Exception as error:  # minidom raises several XML parse exceptions.
        raise BeautifyError(f"invalid XML: {error}") from error
    return dom.toprettyxml(indent=_indent_string(indent))


def beautify_html(html_text: str, indent: int = 4) -> str:
    """Return lightly pretty-printed HTML text."""

    parser = _HTMLBeautifier(_indent_string(indent))
    try:
        parser.feed(html_text)
        parser.close()
    except Exception as error:
        raise BeautifyError(f"invalid HTML: {error}") from error
    return "\n".join(parser.lines)


def detect_syntax(path: str | Path) -> str | None:
    """Return the syntax implied by a path extension, or None if unsupported."""

    return SUPPORTED_SYNTAXES.get(Path(path).suffix.lower())


def _beautify_text(text: str, syntax: str, indent: int) -> str:
    if syntax == "json":
        return beautify_json(text, indent)
    if syntax == "xml":
        return beautify_xml(text, indent)
    if syntax == "html":
        return beautify_html(text, indent)
    raise BeautifyError(f"unsupported syntax: {syntax}")


def beautify_file(path: str | Path, indent: int = 4) -> Path:
    """Beautify one supported file in place and return its path."""

    target = Path(path)
    syntax = detect_syntax(target)
    if syntax is None:
        raise BeautifyError(f"unsupported syntax for file: {target}")
    if not target.exists():
        raise BeautifyError(f"target not found: {target}")
    if not target.is_file():
        raise BeautifyError(f"target is not a file: {target}")

    try:
        source = target.read_text(encoding="utf-8")
        formatted = _beautify_text(source, syntax, indent)
        target.write_text(formatted.rstrip("\n") + "\n", encoding="utf-8")
    except OSError as error:
        raise BeautifyError(f"could not write {target}: {error}") from error
    except BeautifyError as error:
        raise BeautifyError(f"{target}: {error}") from error
    return target


def _iter_supported_files(path: Path, recursive: bool) -> list[Path]:
    iterator = path.rglob("*") if recursive else path.iterdir()
    return sorted(
        (item for item in iterator if item.is_file() and detect_syntax(item) is not None),
        key=lambda item: str(item),
    )


def beautify_paths(path: str | Path, recursive: bool = False, indent: int = 4) -> list[Path]:
    """Beautify one file or supported files under one directory."""

    target = Path(path)
    if not target.exists():
        raise BeautifyError(f"target not found: {target}")
    if target.is_file():
        return [beautify_file(target, indent)]
    if target.is_dir():
        processed = []
        for file_path in _iter_supported_files(target, recursive):
            processed.append(beautify_file(file_path, indent))
        return processed
    raise BeautifyError(f"target is not a file or directory: {target}")


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""

    parser = argparse.ArgumentParser(
        prog=Path(__file__).name,
        description="Beautify JSON, XML, and HTML files in place.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""supported extensions:
  .json, .xml, .html, .htm

behavior:
  Syntax detection is extension-only. Unknown extensions are not content-sniffed.
  File targets are rewritten in place. Directory targets process direct child
  files by default; use -r/--recursive to include subdirectories.

examples:
  beautify.py data.json
  beautify.py . --recursive --indent 2
  beautify.py --tests
""",
    )
    parser.add_argument(
        "path",
        metavar="PATH",
        nargs="?",
        type=Path,
        help="supported file or directory to beautify in place",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="process supported files in subdirectories when PATH is a directory",
    )
    parser.add_argument(
        "-i",
        "--indent",
        metavar="INT",
        default=4,
        type=int,
        help="number of spaces per indentation level (default: 4)",
    )
    parser.add_argument(
        "--tests",
        "--self-test",
        dest="tests",
        action="store_true",
        help="run built-in dependency-free tests and exit",
    )
    return parser


def _capture_main(argv: list[str]) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        try:
            code = main(argv)
        except SystemExit as error:
            code = int(error.code) if isinstance(error.code, int) else 1
    return code, stdout.getvalue(), stderr.getvalue()


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _run_tests() -> bool:
    tests = [
        _test_string_formatters,
        _test_extension_detection,
        _test_single_file_formatting,
        _test_directory_traversal,
        _test_cli_errors_and_noop,
    ]
    failures: list[str] = []
    for test in tests:
        try:
            test()
        except AssertionError as error:
            failures.append(f"{test.__name__}: {error}")

    if failures:
        for failure in failures:
            print(f"[!] {failure}")
        print(f"{len(failures)} failed, {len(tests) - len(failures)} passed")
        return False

    print(f"{len(tests)} tests passed")
    return True


def _test_string_formatters() -> None:
    _assert('"a": 1' in beautify_json('{"a":1}', indent=2), "JSON should be formatted")
    _assert("\n  <child>" in beautify_xml("<root><child>ok</child></root>", indent=2), "XML should be formatted")
    html = beautify_html("<html><body><p>Hi</p><br></body></html>", indent=2)
    _assert("\n  <body>" in html, "HTML body should be indented")
    _assert("<br>" in html, "HTML void tag should be preserved")


def _test_extension_detection() -> None:
    _assert(detect_syntax("data.JSON") == "json", "JSON detection should be case-insensitive")
    _assert(detect_syntax("page.htm") == "html", "HTM should map to HTML")
    _assert(detect_syntax("unknown.txt") is None, "unsupported extensions should not be guessed")


def _test_single_file_formatting() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        json_path = base / "data.json"
        json_path.write_text('{"b":2,"a":1}', encoding="utf-8")
        processed = beautify_file(json_path, indent=2)
        _assert(processed == json_path, "beautify_file should return the processed path")
        _assert('\n  "b": 2' in json_path.read_text(encoding="utf-8"), "JSON file should be indented")

        unsupported = base / "note.txt"
        unsupported.write_text('{"a":1}', encoding="utf-8")
        try:
            beautify_file(unsupported)
        except BeautifyError as error:
            _assert("unsupported syntax" in str(error), "unsupported file should report syntax")
        else:
            raise AssertionError("unsupported single file should fail")


def _test_directory_traversal() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "a.json").write_text('{"a":1}', encoding="utf-8")
        (base / "skip.txt").write_text('{"skip":true}', encoding="utf-8")
        nested = base / "nested"
        nested.mkdir()
        (nested / "b.html").write_text("<main><p>Hi</p></main>", encoding="utf-8")

        direct = beautify_paths(base, recursive=False, indent=2)
        _assert([path.name for path in direct] == ["a.json"], "non-recursive traversal should process direct supported files")
        _assert((base / "skip.txt").read_text(encoding="utf-8") == '{"skip":true}', "unsupported files should be skipped")

        recursive = beautify_paths(base, recursive=True, indent=2)
        _assert([str(path.relative_to(base)) for path in recursive] == ["a.json", str(Path("nested") / "b.html")], "recursive traversal should include nested supported files")


def _test_cli_errors_and_noop() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        empty = base / "empty"
        empty.mkdir()
        code, stdout, stderr = _capture_main([str(empty)])
        _assert(code == 0, f"empty supported directory should be a successful no-op: {stderr}")
        _assert("No supported files found" in stdout, "no-op should be reported")

        missing = base / "missing.json"
        code, _, stderr = _capture_main([str(missing)])
        _assert(code == 1, "missing target should fail")
        _assert("target not found" in stderr, "missing target should be reported")

        unsupported = base / "note.txt"
        unsupported.write_text("hello", encoding="utf-8")
        code, _, stderr = _capture_main([str(unsupported)])
        _assert(code == 1, "unsupported single-file target should fail")
        _assert("unsupported syntax" in stderr, "unsupported syntax should be reported")


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.tests:
        return 0 if _run_tests() else 1
    if args.path is None:
        parser.error("PATH is required unless --tests is used")
    if args.indent < 0:
        parser.error("--indent must be zero or greater")

    try:
        processed = beautify_paths(args.path, recursive=args.recursive, indent=args.indent)
    except BeautifyError as error:
        print(f"[!] {error}", file=sys.stderr)
        return 1

    if not processed:
        print(f"[*] No supported files found: {args.path}")
        return 0

    for path in processed:
        print(f"[+] Beautified: {path}")
    print(f"[*] {len(processed)} file(s) processed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
