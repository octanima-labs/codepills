#!/usr/bin/env python3
# CODEPILLS-META-BEGIN
# schema: codepills.tool/v1
# name: codepills
# version: 1.0.0
# author: octanima-labs
# description: Manage Code Pills metadata checks, imports, and script search.
# repo: https://github.com/octanima-labs/codepills/blob/main/codepills.py
# license: MIT
# usage: python codepills.py check
# tags:
#   - python
#   - cli
#   - metadata
# requires:
#   - Python standard library
# platforms:
#   - Linux
#   - macOS
#   - Windows
# CODEPILLS-META-END

"""Manage Code Pills metadata checks, imports, and script search."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


BEGIN_MARKER = "CODEPILLS-META-BEGIN"
END_MARKER = "CODEPILLS-META-END"
SCRIPT_EXTENSIONS = {".js", ".ps1", ".py", ".sh"}
DESTINATION_DIRS = {
    ".js": "js",
    ".ps1": "powershell",
    ".py": "python",
    ".sh": "bash",
}
LANGUAGE_EXTENSIONS = {
    "bash": ".sh",
    "js": ".js",
    "powershell": ".ps1",
    "python": ".py",
}
DEFAULT_INTERPRETERS = {
    ".js": ["node"],
    ".ps1": ["pwsh", "-NoProfile", "-File"],
    ".py": [sys.executable],
    ".sh": ["bash"],
}
SNIPPET_FILES = {
    Path("bash/snippets.sh"): {"language": "bash", "prefix": "sh", "comment": "#"},
    Path("js/snippets.js"): {"language": "javascript", "prefix": "js", "comment": "//"},
    Path("powershell/snippets.ps1"): {
        "language": "powershell",
        "prefix": "ps",
        "comment": "#",
    },
    Path("python/snippets.py"): {"language": "python", "prefix": "py", "comment": "#"},
}
SNIPPET_PREFIX_TO_PATH = {
    str(config["prefix"]): path for path, config in SNIPPET_FILES.items()
}
REQUIRED_KEYS = (
    "schema",
    "name",
    "version",
    "author",
    "description",
    "repo",
    "license",
    "usage",
    "tags",
    "requires",
    "platforms",
)
LIST_KEYS = {"tags", "requires", "platforms"}
VERSION_PATTERN = re.compile(r"^\d+\.\d+\.\d+$")
SNIPPET_ID_PATTERN = re.compile(r"^### ID: ([a-z]{2}\d{4}) ###$")
SNIPPET_LOOKUP_PATTERN = re.compile(r"^[a-z]{2}\d{4}$")


class MetadataError(ValueError):
    """Raised when a script has invalid CODEPILLS metadata."""


class RunError(ValueError):
    """Raised when a script cannot be resolved or safely executed."""


class EnsurePathError(ValueError):
    """Raised when codepills cannot be installed on PATH."""


def run_git(root: Path, *args: str) -> str | None:
    """Return stripped Git output from the public repo, or None on failure."""
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None

    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value or None


def origin_to_https(remote_url: str | None) -> str:
    """Convert a Git remote URL to a public HTTPS repository URL."""
    if not remote_url:
        return "https://github.com/octanima-labs/codepills"

    if remote_url.startswith("git@github.com:"):
        path = remote_url.removeprefix("git@github.com:").removesuffix(".git")
        return f"https://github.com/{path}"

    if remote_url.startswith("https://"):
        return remote_url.removesuffix(".git")

    return "https://github.com/octanima-labs/codepills"


def repo_base_url(root: Path) -> str:
    """Build the GitHub blob URL prefix for the current public branch."""
    remote_url = origin_to_https(run_git(root, "config", "--get", "remote.origin.url"))
    branch = run_git(root, "branch", "--show-current") or "main"
    return f"{remote_url}/blob/{branch}"


def repo_url_for(path: Path, root: Path) -> str:
    """Return the expected public GitHub URL for a repo file."""
    return f"{repo_base_url(root)}/{path.relative_to(root).as_posix()}"


def git_author(root: Path) -> str:
    """Infer the metadata author from Git config, then commit history."""
    return (
        run_git(root, "config", "--get", "user.name")
        or run_git(root, "log", "-1", "--format=%an")
        or "unknown"
    )


def is_ignored(path: Path, root: Path) -> bool:
    """Return true for files that are not standalone script targets."""
    relative = path.relative_to(root)
    if ".git" in relative.parts:
        return True
    if path.name.startswith("snippets."):
        return True
    return relative.as_posix() == "js/lib.js"


def iter_script_paths(root: Path) -> list[Path]:
    """Collect standalone script candidates by extension."""
    paths = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SCRIPT_EXTENSIONS:
            continue
        if is_ignored(path, root):
            continue
        paths.append(path)
    return sorted(paths)


def strip_line_comment(line: str) -> str:
    """Remove one leading hash comment marker from a metadata line."""
    if not line.startswith("#"):
        raise MetadataError("metadata line is not a hash comment")
    text = line[1:]
    if text.startswith(" "):
        text = text[1:]
    return text


def extract_hash_comment_metadata(lines: list[str]) -> list[str]:
    """Extract metadata from Python and Bash hash-comment headers."""
    start_index = 1 if lines and lines[0].startswith("#!") else 0
    if start_index >= len(lines):
        raise MetadataError("missing metadata header")

    first_line = strip_line_comment(lines[start_index])
    if first_line.strip() != BEGIN_MARKER:
        raise MetadataError("metadata header must start at the top of the file")

    metadata = []
    for line in lines[start_index + 1 :]:
        text = strip_line_comment(line)
        if text.strip() == END_MARKER:
            return metadata
        metadata.append(text)

    raise MetadataError("missing CODEPILLS-META-END marker")


def extract_block_comment_metadata(
    lines: list[str], opener: str, closer: str
) -> list[str]:
    """Extract metadata from a leading block-comment header."""
    if len(lines) < 4:
        raise MetadataError("missing metadata header")
    if lines[0].strip() != opener:
        raise MetadataError("metadata header must be the first block in the file")
    if lines[1].strip() != BEGIN_MARKER:
        raise MetadataError("metadata block must begin with CODEPILLS-META-BEGIN")

    metadata = []
    for index, line in enumerate(lines[2:], start=2):
        if line.strip() == END_MARKER:
            closer_index = index + 1
            if closer_index >= len(lines) or lines[closer_index].strip() != closer:
                raise MetadataError("metadata block comment is not closed immediately")
            return metadata
        metadata.append(line)

    raise MetadataError("missing CODEPILLS-META-END marker")


def extract_metadata_lines(path: Path) -> list[str]:
    """Extract uncommented metadata YAML lines from one script."""
    lines = path.read_text(encoding="utf-8").splitlines()
    suffix = path.suffix.lower()

    if suffix in {".py", ".sh"}:
        return extract_hash_comment_metadata(lines)
    if suffix == ".js":
        return extract_block_comment_metadata(lines, "/*", "*/")
    if suffix == ".ps1":
        return extract_block_comment_metadata(lines, "<#", "#>")

    raise MetadataError(f"unsupported script extension: {suffix}")


def has_metadata_header(path: Path) -> bool:
    """Return true when a file appears to contain a CODEPILLS header."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False
    return BEGIN_MARKER in text or END_MARKER in text


def parse_metadata(lines: list[str]) -> dict[str, object]:
    """Parse the simple YAML subset used by CODEPILLS metadata."""
    data: dict[str, object] = {}
    current_key = None

    for line in lines:
        if not line.strip():
            continue

        if line.startswith((" ", "\t")):
            if current_key is None or current_key not in LIST_KEYS:
                raise MetadataError(f"unexpected indented metadata line: {line!r}")
            item = line.strip()
            if not item.startswith("- "):
                raise MetadataError(f"expected list item in {current_key}: {line!r}")
            value = item[2:].strip()
            if not value:
                raise MetadataError(f"empty list item in {current_key}")
            assert isinstance(data[current_key], list)
            data[current_key].append(value)
            continue

        if ":" not in line:
            raise MetadataError(f"expected key/value metadata line: {line!r}")

        key, raw_value = line.split(":", 1)
        key = key.strip()
        value = raw_value.strip()
        if not key:
            raise MetadataError(f"empty metadata key: {line!r}")
        if key in data:
            raise MetadataError(f"duplicate metadata key: {key}")

        if key in LIST_KEYS:
            if value:
                raise MetadataError(f"{key} must use YAML list items")
            data[key] = []
            current_key = key
        else:
            if not value:
                raise MetadataError(f"empty metadata value for {key}")
            data[key] = value
            current_key = None

    return data


def validate_metadata(
    path: Path,
    root: Path,
    metadata: dict[str, object],
    *,
    validate_repo: bool = True,
) -> list[str]:
    """Return validation errors for parsed metadata."""
    errors = []

    for key in REQUIRED_KEYS:
        if key not in metadata:
            errors.append(f"missing required key: {key}")

    schema = metadata.get("schema")
    if schema is not None and schema != "codepills.tool/v1":
        errors.append("schema must be codepills.tool/v1")

    version = metadata.get("version")
    if isinstance(version, str) and not VERSION_PATTERN.fullmatch(version):
        errors.append("version must use X.Y.Z")

    if validate_repo:
        expected_repo = repo_url_for(path, root)
        repo = metadata.get("repo")
        if repo is not None and repo != expected_repo:
            errors.append(f"repo must be {expected_repo}")

    for key in LIST_KEYS:
        value = metadata.get(key)
        if value is not None and (not isinstance(value, list) or not value):
            errors.append(f"{key} must be a non-empty YAML list")

    return errors


def metadata_to_lines(metadata: dict[str, object]) -> list[str]:
    """Render metadata as the simple YAML subset used by Code Pills."""
    lines = []
    for key in REQUIRED_KEYS:
        value = metadata[key]
        if key in LIST_KEYS:
            lines.append(f"{key}:")
            assert isinstance(value, list)
            for item in value:
                lines.append(f"  - {item}")
        else:
            lines.append(f"{key}: {value}")
    return lines


def comment_metadata_lines(lines: list[str], suffix: str) -> list[str]:
    """Wrap raw metadata lines in the comment style for a script type."""
    if suffix in {".py", ".sh"}:
        commented = [f"# {BEGIN_MARKER}"]
        commented.extend(f"# {line}" if line else "#" for line in lines)
        commented.append(f"# {END_MARKER}")
        return commented

    if suffix == ".js":
        return ["/*", BEGIN_MARKER, *lines, END_MARKER, "*/"]

    if suffix == ".ps1":
        return ["<#", BEGIN_MARKER, *lines, END_MARKER, "#>"]

    raise MetadataError(f"unsupported script extension: {suffix}")


def default_metadata(source: Path, destination: Path, root: Path) -> dict[str, object]:
    """Generate conservative metadata for an imported script."""
    suffix = destination.suffix.lower()
    stem_name = destination.stem.replace("_", "-").lower()

    language_defaults = {
        ".py": {
            "description": f"Run the {stem_name} Python script.",
            "usage": f"python {destination.relative_to(root).as_posix()}",
            "tags": ["python", "script"],
            "requires": ["Python standard library"],
            "platforms": ["Linux", "macOS", "Windows"],
        },
        ".sh": {
            "description": f"Run the {stem_name} Bash script.",
            "usage": f"bash {destination.relative_to(root).as_posix()}",
            "tags": ["bash", "script"],
            "requires": ["bash"],
            "platforms": ["Linux", "macOS"],
        },
        ".ps1": {
            "description": f"Run the {stem_name} PowerShell script.",
            "usage": f"pwsh -NoProfile -File {destination.relative_to(root).as_posix()}",
            "tags": ["powershell", "script"],
            "requires": ["PowerShell"],
            "platforms": ["Windows", "Linux", "macOS"],
        },
        ".js": {
            "description": f"Run the {stem_name} JavaScript script.",
            "usage": f"node {destination.relative_to(root).as_posix()}",
            "tags": ["javascript", "script"],
            "requires": ["JavaScript runtime"],
            "platforms": ["Linux", "macOS", "Windows"],
        },
    }

    defaults = language_defaults[suffix]
    return {
        "schema": "codepills.tool/v1",
        "name": stem_name,
        "version": "0.1.0",
        "author": git_author(root),
        "description": defaults["description"],
        "repo": repo_url_for(destination, root),
        "license": "MIT",
        "usage": defaults["usage"],
        "tags": defaults["tags"],
        "requires": defaults["requires"],
        "platforms": defaults["platforms"],
    }


def insert_metadata_header(source: Path, destination: Path, metadata: dict[str, object]) -> None:
    """Copy source to destination with a generated metadata header."""
    suffix = destination.suffix.lower()
    lines = source.read_text(encoding="utf-8").splitlines()
    body = lines
    prefix = []

    if suffix in {".py", ".sh"} and lines and lines[0].startswith("#!"):
        prefix = [lines[0]]
        body = lines[1:]

    header = comment_metadata_lines(metadata_to_lines(metadata), suffix)
    output_lines = [*prefix, *header, "", *body]
    destination.write_text("\n".join(output_lines) + "\n", encoding="utf-8")


def copy_with_existing_metadata(source: Path, destination: Path, root: Path) -> list[str]:
    """Copy a valid metadata-bearing script, updating only its repo URL."""
    try:
        metadata = parse_metadata(extract_metadata_lines(source))
    except (OSError, UnicodeDecodeError, MetadataError) as error:
        return [str(error)]

    errors = validate_metadata(source, root, metadata, validate_repo=False)
    if errors:
        return errors

    shutil.copyfile(source, destination)
    metadata["repo"] = repo_url_for(destination, root)
    update_metadata_header(destination, metadata)
    return []


def update_metadata_header(path: Path, metadata: dict[str, object]) -> None:
    """Replace the leading metadata header in an existing script."""
    suffix = path.suffix.lower()
    lines = path.read_text(encoding="utf-8").splitlines()
    start = 1 if suffix in {".py", ".sh"} and lines and lines[0].startswith("#!") else 0
    header = comment_metadata_lines(metadata_to_lines(metadata), suffix)

    if suffix in {".py", ".sh"}:
        end = None
        for index in range(start, len(lines)):
            if strip_line_comment(lines[index]).strip() == END_MARKER:
                end = index + 1
                break
        if end is None:
            raise MetadataError("missing CODEPILLS-META-END marker")
    else:
        end = None
        for index in range(start, len(lines)):
            if lines[index].strip() == END_MARKER:
                end = index + 2
                break
        if end is None:
            raise MetadataError("missing CODEPILLS-META-END marker")

    output_lines = [*lines[:start], *header, *lines[end:]]
    path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")


def check_file(path: Path, root: Path) -> list[str]:
    """Validate one script and return human-readable errors."""
    try:
        metadata_lines = extract_metadata_lines(path)
        metadata = parse_metadata(metadata_lines)
    except (OSError, UnicodeDecodeError, MetadataError) as error:
        return [str(error)]

    return validate_metadata(path, root, metadata)


def selected_script_metadata(path: Path, root: Path) -> tuple[dict[str, object], list[str]]:
    """Parse and validate metadata for one selected standalone script."""
    try:
        metadata = parse_metadata(extract_metadata_lines(path))
    except (OSError, UnicodeDecodeError, MetadataError) as error:
        return {}, [str(error)]
    return metadata, validate_metadata(path, root, metadata)


def resolve_run_script(script: str, root: Path) -> Path:
    """Resolve a run target like python/pingwave to a standalone script path."""
    if script in {"codepills", "codepills.py"}:
        raise RunError("codepills cannot run itself")

    requested = Path(script)
    if requested.is_absolute():
        raise RunError("SCRIPT must be a relative path")
    if any(part in {"", ".", ".."} for part in requested.parts):
        raise RunError("SCRIPT must not contain empty, current, or parent path parts")
    if len(requested.parts) != 2:
        raise RunError("SCRIPT must use <language>/<name>")

    language, name = requested.parts
    expected_extension = LANGUAGE_EXTENSIONS.get(language)
    if expected_extension is None:
        languages = ", ".join(sorted(LANGUAGE_EXTENSIONS))
        raise RunError(f"unknown language directory {language!r}; expected one of {languages}")

    name_path = Path(name)
    if name_path.name != name:
        raise RunError("SCRIPT name must not contain path separators")
    if name.startswith("snippets"):
        raise RunError("snippets cannot be run with this command")

    suffix = name_path.suffix
    if suffix and suffix != expected_extension:
        raise RunError(f"{language} scripts must use {expected_extension}")

    filename = name if suffix else f"{name}{expected_extension}"
    path = root / language / filename
    if not path.is_file():
        raise RunError(f"script not found: {language}/{filename}")
    if path.resolve() == Path(__file__).resolve():
        raise RunError("codepills cannot run itself")
    if is_ignored(path, root):
        raise RunError("target is not a standalone script")
    if path.suffix.lower() not in SCRIPT_EXTENSIONS:
        raise RunError(f"unsupported script extension: {path.suffix}")
    return path


def has_shebang(path: Path) -> bool:
    """Return true when a script starts with a shebang."""
    try:
        with path.open("rb") as handle:
            return handle.read(2) == b"#!"
    except OSError:
        return False


def run_command_for(path: Path, args: list[str]) -> list[str]:
    """Build the child command for one standalone script."""
    if has_shebang(path):
        return [str(path), *args]

    interpreter = DEFAULT_INTERPRETERS.get(path.suffix.lower())
    if interpreter is None:
        raise RunError(f"unsupported script extension: {path.suffix}")
    return [*interpreter, str(path), *args]


def is_browser_script(metadata: dict[str, object]) -> bool:
    """Return true when metadata marks a JavaScript script as browser-only."""
    tags = metadata.get("tags", [])
    if not isinstance(tags, list):
        return False
    return any(str(tag).casefold() == "browser" for tag in tags)


def user_bin_dir() -> Path:
    """Return the per-user bin directory used for the codepills command."""
    if os.name == "nt":
        base = os.environ.get("USERPROFILE") or str(Path.home())
        return Path(base) / ".local" / "bin"
    return Path.home() / ".local" / "bin"


def path_entries() -> list[Path]:
    """Return current PATH entries as expanded paths."""
    return [Path(entry).expanduser() for entry in os.environ.get("PATH", "").split(os.pathsep) if entry]


def is_on_path(directory: Path) -> bool:
    """Return true when a directory is already present in the current PATH."""
    target = directory.expanduser()
    for entry in path_entries():
        try:
            if entry.resolve() == target.resolve():
                return True
        except OSError:
            if entry == target:
                return True
    return False


def shell_config_path() -> Path:
    """Choose a shell startup file for adding ~/.local/bin to PATH."""
    shell = Path(os.environ.get("SHELL", "")).name
    home = Path.home()

    if shell == "bash":
        return home / ".bashrc"
    if shell == "zsh":
        return home / ".zshrc"
    if shell == "fish":
        return home / ".config" / "fish" / "config.fish"
    return home / ".profile"


def ensure_posix_path(directory: Path) -> str | None:
    """Ensure the user bin directory is added to a future shell PATH."""
    if is_on_path(directory):
        return None

    config_path = shell_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    if config_path.exists():
        current = config_path.read_text(encoding="utf-8")
    else:
        current = ""

    directory_text = str(directory)
    if directory_text in current:
        return f"{directory} is already mentioned in {config_path}"

    if config_path.name == "config.fish":
        block = f"\n# Code Pills\nfish_add_path {directory_text}\n"
    else:
        block = (
            "\n# Code Pills\n"
            f"export PATH=\"{directory_text}:$PATH\"\n"
        )
    config_path.write_text(current.rstrip("\n") + block, encoding="utf-8")
    return f"added {directory} to PATH in {config_path}"


def ensure_posix_executable(script_path: Path) -> str | None:
    """Ensure the codepills script has the user executable bit set."""
    mode = script_path.stat().st_mode
    if mode & 0o100:
        return None
    script_path.chmod(mode | 0o100)
    return f"made {script_path.name} executable"


def ensure_posix_command(script_path: Path, directory: Path) -> str | None:
    """Ensure ~/.local/bin/codepills points to this codepills.py file."""
    directory.mkdir(parents=True, exist_ok=True)
    link_path = directory / "codepills"
    if link_path.exists() or link_path.is_symlink():
        if link_path.is_symlink() and link_path.resolve() == script_path.resolve():
            return None
        raise EnsurePathError(f"{link_path} already exists and is not managed by this repo")

    link_path.symlink_to(script_path)
    return f"created {link_path} -> {script_path}"


def ensure_windows_path(directory: Path) -> str | None:
    """Ensure the Windows user PATH includes the user bin directory."""
    try:
        import winreg
    except ImportError as error:
        raise EnsurePathError("winreg is unavailable on this platform") from error

    directory_text = str(directory)
    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        "Environment",
        0,
        winreg.KEY_READ | winreg.KEY_WRITE,
    ) as key:
        try:
            value, value_type = winreg.QueryValueEx(key, "Path")
        except FileNotFoundError:
            value = ""
            value_type = winreg.REG_EXPAND_SZ

        entries = [entry for entry in value.split(os.pathsep) if entry]
        if any(entry.casefold() == directory_text.casefold() for entry in entries):
            return None

        new_value = os.pathsep.join([*entries, directory_text]) if entries else directory_text
        winreg.SetValueEx(key, "Path", 0, value_type, new_value)
    return f"added {directory} to the Windows user PATH"


def ensure_windows_command(script_path: Path, directory: Path) -> str | None:
    """Create a Windows command shim for codepills."""
    directory.mkdir(parents=True, exist_ok=True)
    shim_path = directory / "codepills.cmd"
    shim = f'@echo off\r\n"{sys.executable}" "{script_path}" %*\r\n'

    if shim_path.exists():
        if shim_path.read_text(encoding="utf-8") == shim:
            return None
        raise EnsurePathError(f"{shim_path} already exists and is not managed by this repo")

    shim_path.write_text(shim, encoding="utf-8")
    return f"created {shim_path}"


def ensure_codepills_on_path(root: Path) -> list[str]:
    """Ensure codepills is invokable as a direct command."""
    script_path = root / "codepills.py"
    directory = user_bin_dir()
    actions = []

    if os.name == "nt":
        command_action = ensure_windows_command(script_path, directory)
        path_action = ensure_windows_path(directory)
    else:
        executable_action = ensure_posix_executable(script_path)
        if executable_action:
            actions.append(executable_action)
        command_action = ensure_posix_command(script_path, directory)
        path_action = ensure_posix_path(directory)

    if command_action:
        actions.append(command_action)
    if path_action:
        actions.append(path_action)
    return actions


def strip_snippet_comment(line: str, comment: str) -> str | None:
    """Return uncommented snippet metadata text, or None for non-comment lines."""
    if not line.startswith(comment):
        return None
    text = line[len(comment) :]
    if text.startswith(" "):
        text = text[1:]
    return text


def parse_snippet_list(
    lines: list[str], index: int, section_end: int, comment: str
) -> tuple[list[str], int, list[str]]:
    """Parse a non-empty list from snippet header comment lines."""
    values = []
    errors = []

    while index < section_end:
        text = strip_snippet_comment(lines[index], comment)
        if text is None or not text.startswith("- "):
            break
        value = text[2:].strip()
        if value:
            values.append(value)
        else:
            errors.append(f"line {index + 1}: empty snippet list item")
        index += 1

    if not values:
        errors.append(f"line {index + 1}: expected at least one list item")
    return values, index, errors


def trim_boundary_blank_lines(lines: list[str]) -> list[str]:
    """Trim blank lines around snippet content while preserving internal text."""
    start = 0
    end = len(lines)

    while start < end and not lines[start].strip():
        start += 1
    while end > start and not lines[end - 1].strip():
        end -= 1

    return lines[start:end]


def parse_snippet_section(
    path: Path,
    root: Path,
    lines: list[str],
    start: int,
    end: int,
    prefix: str,
    comment: str,
) -> tuple[dict[str, object] | None, list[str]]:
    """Parse one normalized snippet section."""
    errors = []
    marker = strip_snippet_comment(lines[start], comment)
    if marker is None:
        return None, [f"line {start + 1}: snippet marker must be commented"]

    match = SNIPPET_ID_PATTERN.fullmatch(marker)
    if not match:
        return None, [f"line {start + 1}: invalid snippet ID marker"]

    snippet_id = match.group(1)
    if not snippet_id.startswith(prefix):
        errors.append(
            f"line {start + 1}: snippet ID {snippet_id} must use {prefix} prefix"
        )

    index = start + 1
    required_headers = (("Title", "name"), ("Description", "description"))
    record: dict[str, object] = {
        "type": "snippet",
        "id": snippet_id,
        "path": f"{path.relative_to(root).as_posix()}#{snippet_id}",
    }

    for label, key in required_headers:
        if index >= end:
            errors.append(f"line {start + 1}: missing {label} header")
            break
        text = strip_snippet_comment(lines[index], comment)
        expected = f"{label}:"
        if text is None or not text.startswith(expected):
            errors.append(f"line {index + 1}: expected {expected} header")
        else:
            value = text[len(expected) :].strip()
            if value:
                record[key] = value
            else:
                errors.append(f"line {index + 1}: {label} cannot be empty")
        index += 1

    for label, key in (("Tags", "tags"), ("Platforms", "platforms")):
        if index >= end:
            errors.append(f"line {start + 1}: missing {label} header")
            break
        text = strip_snippet_comment(lines[index], comment)
        expected = f"{label}:"
        if text != expected:
            errors.append(f"line {index + 1}: expected {expected} header")
            index += 1
            continue
        values, index, list_errors = parse_snippet_list(lines, index + 1, end, comment)
        errors.extend(list_errors)
        record[key] = values

    while index < end and not lines[index].strip():
        index += 1

    content = trim_boundary_blank_lines(lines[index:end])
    if not any(line.strip() for line in content):
        errors.append(f"line {start + 1}: snippet content cannot be empty")
    else:
        record["content"] = "\n".join(content)

    for key in ("name", "description", "tags", "platforms"):
        if key not in record:
            errors.append(f"line {start + 1}: missing parsed {key}")

    return (None if errors else record), errors


def parse_snippet_file(path: Path, root: Path) -> tuple[list[dict[str, object]], list[str]]:
    """Parse normalized snippets from one snippets file."""
    relative = path.relative_to(root)
    config = SNIPPET_FILES.get(relative)
    if config is None:
        return [], [f"unsupported snippets file: {relative}"]

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as error:
        return [], [str(error)]

    comment = str(config["comment"])
    prefix = str(config["prefix"])
    marker_indexes = []
    errors = []

    for index, line in enumerate(lines):
        text = strip_snippet_comment(line, comment)
        if text and text.startswith("### ID:"):
            if SNIPPET_ID_PATTERN.fullmatch(text):
                marker_indexes.append(index)
            else:
                errors.append(f"line {index + 1}: invalid snippet ID marker")

    if not marker_indexes:
        errors.append("missing snippet ID markers")
        return [], errors

    records = []
    seen_ids = set()
    for position, start in enumerate(marker_indexes):
        end = marker_indexes[position + 1] if position + 1 < len(marker_indexes) else len(lines)
        record, section_errors = parse_snippet_section(
            path, root, lines, start, end, prefix, comment
        )
        errors.extend(section_errors)
        if record is None:
            continue

        snippet_id = str(record["id"])
        if snippet_id in seen_ids:
            errors.append(f"line {start + 1}: duplicate snippet ID {snippet_id}")
            continue
        seen_ids.add(snippet_id)
        records.append(record)

    return ([] if errors else records), errors


def iter_snippet_paths(root: Path) -> list[Path]:
    """Return existing snippets files that should be validated and searched."""
    paths = []
    for relative in SNIPPET_FILES:
        path = root / relative
        if path.exists():
            paths.append(path)
    return sorted(paths)


def check_snippet_file(path: Path, root: Path) -> list[str]:
    """Validate one snippets notebook and return human-readable errors."""
    _records, errors = parse_snippet_file(path, root)
    return errors


def find_snippet(snippet_id: str, root: Path) -> tuple[dict[str, object] | None, list[str]]:
    """Find one normalized snippet record by ID."""
    normalized_id = snippet_id.casefold()
    if not SNIPPET_LOOKUP_PATTERN.fullmatch(normalized_id):
        return None, ["snippet ID must look like py0001, sh0001, ps0001, or js0001"]

    relative_path = SNIPPET_PREFIX_TO_PATH.get(normalized_id[:2])
    if relative_path is None:
        return None, [f"snippet not found: {normalized_id}"]

    path = root / relative_path
    if not path.exists():
        return None, [f"snippet not found: {normalized_id}"]

    records, errors = parse_snippet_file(path, root)
    if errors:
        return None, [f"{relative_path}:", *[f"  - {error}" for error in errors]]

    matches = [record for record in records if str(record.get("id", "")).casefold() == normalized_id]
    if not matches:
        return None, [f"snippet not found: {normalized_id}"]
    if len(matches) > 1:
        return None, [f"duplicate snippet ID: {normalized_id}"]
    return matches[0], []


def clipboard_commands() -> list[list[str]]:
    """Return platform clipboard commands in preferred order."""
    if sys.platform == "darwin":
        return [["pbcopy"]]
    if sys.platform.startswith("win"):
        return [["clip"], ["powershell", "-NoProfile", "-Command", "Set-Clipboard"]]

    if os.environ.get("WAYLAND_DISPLAY"):
        return [
            ["wl-copy"],
            ["xclip", "-selection", "clipboard"],
            ["xsel", "--clipboard", "--input"],
        ]

    if os.environ.get("DISPLAY"):
        return [
            ["xclip", "-selection", "clipboard"],
            ["xsel", "--clipboard", "--input"],
            ["wl-copy"],
        ]

    return [
        ["wl-copy"],
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
    ]


def copy_to_clipboard(text: str) -> str | None:
    """Copy text to the system clipboard, returning a warning on failure."""
    attempted = []
    for command in clipboard_commands():
        executable = command[0]
        if shutil.which(executable) is None:
            continue

        attempted.append(executable)
        try:
            completed = subprocess.run(
                command,
                input=text,
                text=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=2,
            )
        except subprocess.TimeoutExpired:
            continue
        except OSError as error:
            attempted[-1] = f"{executable} ({error})"
            continue

        if completed.returncode == 0:
            return None

    if attempted:
        return "clipboard copy failed: tried " + ", ".join(attempted)
    commands = ", ".join(command[0] for command in clipboard_commands())
    return f"no clipboard command found; install one of: {commands}"


def load_search_records(root: Path) -> list[dict[str, object]]:
    """Load valid metadata records for searchable scripts and snippets."""
    records = []
    for path in iter_script_paths(root):
        try:
            metadata = parse_metadata(extract_metadata_lines(path))
        except (OSError, UnicodeDecodeError, MetadataError) as error:
            print(
                f"warning: skipping {path.relative_to(root)}: {error}",
                file=sys.stderr,
            )
            continue

        errors = validate_metadata(path, root, metadata)
        if errors:
            print(f"warning: skipping {path.relative_to(root)}:", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
            continue

        metadata["type"] = "script"
        metadata["id"] = ""
        metadata["path"] = path.relative_to(root).as_posix()
        records.append(metadata)

    for path in iter_snippet_paths(root):
        snippet_records, errors = parse_snippet_file(path, root)
        if errors:
            print(f"warning: skipping {path.relative_to(root)}:", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
            continue
        records.extend(snippet_records)

    return records


def text_matches(value: object, filters: list[str] | None) -> bool:
    """Return true when a string value contains every filter substring."""
    if not filters:
        return True
    text = str(value).casefold()
    return all(item.casefold() in text for item in filters)


def list_matches(value: object, filters: list[str] | None) -> bool:
    """Return true when a list contains every requested value."""
    if not filters:
        return True
    if not isinstance(value, list):
        return False

    items = {str(item).casefold() for item in value}
    return all(item.casefold() in items for item in filters)


def record_matches(record: dict[str, object], args: argparse.Namespace) -> bool:
    """Apply all search filters to one metadata record."""
    if args.item_type and str(record.get("type", "")).casefold() not in args.item_type:
        return False

    return (
        text_matches(record.get("name", ""), args.name)
        and text_matches(record.get("description", ""), args.description)
        and list_matches(record.get("tags", []), args.tag)
        and list_matches(record.get("platforms", []), args.platform)
    )


def format_list(value: object) -> str:
    """Format a metadata list for table output."""
    if not isinstance(value, list):
        return ""
    return ", ".join(str(item) for item in value)


def record_identifier(record: dict[str, object]) -> str:
    """Return the unique identifier shown in search results."""
    if record.get("type") == "snippet":
        return str(record.get("id", ""))
    return str(record.get("path", ""))


def print_search_table(records: list[dict[str, object]], *, details: bool) -> None:
    """Print search matches as a compact aligned table."""
    if details:
        rows = [
            (
                str(record.get("type", "")),
                record_identifier(record),
                str(record.get("name", "")),
                str(record.get("description", "")),
                format_list(record.get("tags", [])),
                format_list(record.get("platforms", [])),
            )
            for record in records
        ]
        headers = ("TYPE", "IDENTIFIER", "NAME", "DESCRIPTION", "TAGS", "PLATFORMS")
    else:
        rows = [
            (
                str(record.get("type", "")),
                record_identifier(record),
                str(record.get("name", "")),
                format_list(record.get("platforms", [])),
            )
            for record in records
        ]
        headers = ("TYPE", "IDENTIFIER", "NAME", "PLATFORMS")

    widths = [
        max(len(row[index]) for row in [headers, *rows])
        for index in range(len(headers))
    ]

    print("  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in rows:
        print("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))


def command_check(_args: argparse.Namespace, root: Path) -> int:
    """Validate standalone script metadata headers and snippet notebooks."""
    failures: dict[Path, list[str]] = {}

    for path in iter_script_paths(root):
        errors = check_file(path, root)
        if errors:
            failures[path.relative_to(root)] = errors

    for path in iter_snippet_paths(root):
        errors = check_snippet_file(path, root)
        if errors:
            failures[path.relative_to(root)] = errors

    if failures:
        for path, errors in failures.items():
            print(f"{path}:", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
        return 1

    print("CODEPILLS metadata headers and snippets are valid.")
    return 0


def command_import(args: argparse.Namespace, root: Path) -> int:
    """Import an existing script into the public repo."""
    source = Path(args.path).expanduser().resolve()
    if not source.is_file():
        print(f"error: source is not a file: {source}", file=sys.stderr)
        return 1

    suffix = source.suffix.lower()
    if suffix not in DESTINATION_DIRS:
        supported = ", ".join(sorted(DESTINATION_DIRS))
        print(f"error: unsupported extension {suffix!r}; expected one of {supported}", file=sys.stderr)
        return 1

    stem = args.name if args.name else source.stem
    if not stem or "/" in stem or "\\" in stem or Path(stem).suffix:
        print("error: --name must be a filename stem without path or extension", file=sys.stderr)
        return 1

    destination = root / DESTINATION_DIRS[suffix] / f"{stem}{source.suffix}"
    if destination.exists():
        print(f"error: destination already exists: {destination.relative_to(root)}", file=sys.stderr)
        return 1

    destination.parent.mkdir(parents=True, exist_ok=True)
    if has_metadata_header(source):
        errors = copy_with_existing_metadata(source, destination, root)
        if errors:
            destination.unlink(missing_ok=True)
            print(f"error: source metadata is invalid: {source}", file=sys.stderr)
            for error in errors:
                print(f"  - {error}", file=sys.stderr)
            return 1
    else:
        metadata = default_metadata(source, destination, root)
        insert_metadata_header(source, destination, metadata)

    print(f"Imported {source} -> {destination.relative_to(root)}")
    return 0


def command_search(args: argparse.Namespace, root: Path) -> int:
    """Search standalone scripts by metadata fields."""
    records = [
        record for record in load_search_records(root) if record_matches(record, args)
    ]

    if not records:
        print("No matches found.")
        return 1

    print_search_table(records, details=args.details)
    return 0


def command_run(args: argparse.Namespace, root: Path) -> int:
    """Run a selected standalone script and pass through remaining arguments."""
    try:
        script_path = resolve_run_script(args.script, root)
    except RunError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    metadata, errors = selected_script_metadata(script_path, root)
    if errors:
        print(f"error: selected script metadata is invalid: {script_path.relative_to(root)}", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    if script_path.suffix.lower() == ".js" and is_browser_script(metadata):
        print(
            f"error: {script_path.relative_to(root)} is a browser JavaScript script and cannot be run here",
            file=sys.stderr,
        )
        return 1

    try:
        command = run_command_for(script_path, args.script_args)
        completed = subprocess.run(command, check=False)
    except FileNotFoundError as error:
        print(f"error: command not found: {error.filename}", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"error: could not run {script_path.relative_to(root)}: {error}", file=sys.stderr)
        return 1

    return completed.returncode


def command_get(args: argparse.Namespace, root: Path) -> int:
    """Print snippets by ID and copy their combined content to the clipboard."""
    records = []
    errors = []

    for snippet_id in args.snippet_ids:
        record, snippet_errors = find_snippet(snippet_id, root)
        errors.extend(snippet_errors)
        if record is not None:
            records.append(record)

    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1

    content = "\n\n\n".join(str(record.get("content", "")) for record in records)
    sys.stdout.write(content)
    if not content.endswith("\n"):
        sys.stdout.write("\n")

    warning = copy_to_clipboard(content)
    if warning:
        print(f"warning: {warning}", file=sys.stderr)
    return 0


def command_ensurepath(_args: argparse.Namespace, root: Path) -> int:
    """Ensure codepills can be run as a direct command."""
    try:
        actions = ensure_codepills_on_path(root)
    except EnsurePathError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except OSError as error:
        print(f"error: could not update PATH installation: {error}", file=sys.stderr)
        return 1

    if actions:
        for action in actions:
            print(action)
    else:
        print("codepills is already available on PATH")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the Code Pills command-line parser."""
    parser = argparse.ArgumentParser(
        prog="codepills",
        description="Manage Code Pills scripts and metadata.",
    )
    subparsers = parser.add_subparsers(dest="command")

    check_parser = subparsers.add_parser(
        "check",
        help="validate metadata headers on standalone scripts",
    )
    check_parser.set_defaults(func=command_check)

    ensurepath_parser = subparsers.add_parser(
        "ensurepath",
        help="install the codepills command in the user PATH",
    )
    ensurepath_parser.set_defaults(func=command_ensurepath)

    import_parser = subparsers.add_parser(
        "import",
        help="import a script into the repo and add metadata",
    )
    import_parser.add_argument("path", metavar="PATH", help="script file to import")
    import_parser.add_argument(
        "-n",
        "--name",
        metavar="NAME",
        help="destination filename stem without extension",
    )
    import_parser.set_defaults(func=command_import)

    get_parser = subparsers.add_parser(
        "get",
        help="print a snippet by ID and copy it to the clipboard",
    )
    get_parser.add_argument(
        "snippet_ids",
        metavar="SNIPPET_ID",
        nargs="+",
        help="snippet identifier like py0001, sh0001, ps0001, or js0001",
    )
    get_parser.set_defaults(func=command_get)

    search_parser = subparsers.add_parser(
        "search",
        help="search scripts and snippets by metadata",
    )
    search_parser.add_argument(
        "--type",
        dest="item_type",
        action="append",
        choices=("script", "snippet"),
        help="match only scripts or snippets; can be repeated",
    )
    search_parser.add_argument(
        "-D",
        "--details",
        action="store_true",
        help="include description and tags columns in search output",
    )
    search_parser.add_argument(
        "-n",
        "--name",
        action="append",
        help="match scripts whose name contains this substring",
    )
    search_parser.add_argument(
        "-d",
        "--description",
        action="append",
        help="match scripts whose description contains this substring",
    )
    search_parser.add_argument(
        "-t",
        "--tag",
        action="append",
        help="match scripts containing this tag; can be repeated",
    )
    search_parser.add_argument(
        "-p",
        "--platform",
        action="append",
        help="match scripts containing this platform; can be repeated",
    )
    search_parser.set_defaults(func=command_search)

    run_parser = subparsers.add_parser(
        "run",
        help="run a standalone script by <language>/<name>",
    )
    run_parser.add_argument(
        "script",
        metavar="SCRIPT",
        help="repo-relative script reference like python/pingwave or powershell/barabara.ps1",
    )
    run_parser.add_argument(
        "script_args",
        metavar="ARGS",
        nargs=argparse.REMAINDER,
        help="arguments passed through to the selected script",
    )
    run_parser.set_defaults(func=command_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the Code Pills CLI."""
    root = Path(__file__).resolve().parent
    parser = build_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "func"):
        parser.print_help(sys.stderr)
        return 2

    return args.func(args, root)


if __name__ == "__main__":
    raise SystemExit(main())
