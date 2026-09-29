# CODEPILLS-META-BEGIN
# schema: codepills.tool/v1
# name: freezenv
# version: 1.1.0
# author: octanima-labs
# description: Generate auto_requirements.txt from packages installed in a Python virtual environment.
# repo: https://github.com/octanima-labs/codepills/blob/main/python/freezenv.py
# license: MIT
# usage: python python/freezenv.py [-r|--recursive] [PATH]
# tags:
#   - python
#   - cli
#   - virtualenv
# requires:
#   - Python standard library
# platforms:
#   - Linux
#   - macOS
#   - Windows
# CODEPILLS-META-END

"""Generate a requirements file from an existing Python virtual environment.

``freezenv`` is a small, dependency-free alternative to running ``pip freeze``
inside a virtual environment. It scans package metadata from a venv located at
the provided path, ``venv`` subdirectory, or ``.venv`` subdirectory, then writes
the discovered packages to ``auto_requirements.txt``. In recursive mode, it
finds every virtual environment under the provided path and freezes each one.

Examples:
    Generate requirements for the current directory::

        python freezenv.py

    Generate requirements for a specific project directory::

        python freezenv.py /path/to/project

    Generate requirements for every venv below a directory::

        python freezenv.py --recursive /path/to/projects

    Run the built-in self-tests::

        python freezenv.py --tests
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path


BASE_PACKAGES = {"pip", "setuptools", "wheel", "distribute"}
OUTPUT_FILENAME = "auto_requirements.txt"

__all__ = [
    "BASE_PACKAGES",
    "OUTPUT_FILENAME",
    "FreezenvError",
    "discover_venv",
    "discover_venvs_recursive",
    "find_site_packages",
    "freeze_requirements",
    "write_requirements",
    "freeze_venv",
]


class FreezenvError(ValueError):
    """Raised when requirements cannot be generated from a virtual environment."""


def discover_venv(path: str | os.PathLike[str]) -> Path:
    """Return the venv path found at path, path/venv, or path/.venv."""

    base = Path(path)
    for name in ("", "venv", ".venv"):
        candidate = base / name
        if (candidate / "pyvenv.cfg").exists():
            return candidate

    raise FreezenvError("No virtual environment found at the provided path or subdirectories.")


def discover_venvs_recursive(path: str | os.PathLike[str]) -> list[Path]:
    """Return all virtual environment directories found below path."""

    venvs = []
    for current_root, dirnames, filenames in os.walk(path):
        if "pyvenv.cfg" in filenames:
            venvs.append(Path(current_root))
            dirnames[:] = []

    return sorted(venvs, key=lambda item: str(item).lower())


def find_site_packages(venv_path: str | os.PathLike[str]) -> Path:
    """Return a platform-specific site-packages directory for a virtual environment."""

    target_venv = Path(venv_path)
    possible_site_paths = [
        target_venv / "Lib" / "site-packages",
        target_venv / "lib64" / "site-packages",
    ]

    lib_dir = target_venv / "lib"
    if lib_dir.exists():
        for item in lib_dir.iterdir():
            if item.name.startswith("python"):
                possible_site_paths.append(item / "site-packages")

    for site_packages in possible_site_paths:
        if site_packages.exists():
            return site_packages

    raise FreezenvError("Could not locate site-packages directory.")


def freeze_requirements(path: str | os.PathLike[str]) -> list[str]:
    """Return sorted requirement strings from package metadata in a venv."""

    site_packages = find_site_packages(discover_venv(path))
    dependencies = []

    for folder in os.listdir(site_packages):
        if not folder.endswith(".dist-info"):
            continue

        metadata_path = site_packages / folder / "METADATA"
        if not metadata_path.exists():
            continue

        name = None
        version = None
        with metadata_path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("Name:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("Version:"):
                    version = line.split(":", 1)[1].strip()

                if name and version:
                    if name.lower() not in BASE_PACKAGES:
                        dependencies.append(f"{name}=={version}")
                    break

    return sorted(set(dependencies), key=str.lower)


def write_requirements(
    path: str | os.PathLike[str],
    requirements: list[str] | None = None,
    output: str | os.PathLike[str] | None = None,
) -> Path:
    """Write requirement strings to a file and return the output path."""

    dependencies = freeze_requirements(path) if requirements is None else requirements
    output_file = Path(output) if output is not None else Path(path) / OUTPUT_FILENAME
    output_file.write_text("\n".join(dependencies), encoding="utf-8")
    return output_file


def _recursive_output_dir(venv_path: Path) -> Path:
    """Return the output directory for a recursively discovered venv."""

    if venv_path.name in {"venv", ".venv"}:
        return venv_path.parent
    return venv_path


def freeze_venv(
    path: str | os.PathLike[str], recursive: bool = False
) -> list[str] | str | dict[str, list[str] | str]:
    """Create ``auto_requirements.txt`` from package metadata in one or more venvs.

    In non-recursive mode, the function looks for a virtual environment in
    three locations, in order: the provided ``path`` itself, ``path/venv``, and
    ``path/.venv``. Once found, it locates a platform-specific ``site-packages``
    directory and reads each package's ``.dist-info/METADATA`` file to collect
    ``Name`` and ``Version``.

    In recursive mode, the function freezes every virtual environment below the
    provided ``path``. For discovered ``venv`` and ``.venv`` directories, output
    is written to the parent project directory; otherwise, output is written to
    the virtual environment directory itself.

    Base packaging tools such as ``pip`` and ``setuptools`` are omitted. The
    remaining dependencies are deduplicated and sorted case-insensitively.

    Args:
        path: Directory containing a venv directly, or containing ``venv`` or
            ``.venv`` as a subdirectory. In recursive mode, directory to scan.
        recursive: Whether to scan for and freeze every virtual environment
            below ``path``.

    Returns:
        In non-recursive mode, returns a sorted list of ``name==version``
        requirement strings on success, or an error string beginning with
        ``"Error:"`` on failure. In recursive mode, returns a dictionary keyed
        by venv path, where each value is either a sorted requirement list or an
        error string beginning with ``"Error:"``.
    """
    if recursive:
        venvs = discover_venvs_recursive(path)
        if not venvs:
            return {str(Path(path)): "Error: No virtual environments found under the provided path."}

        results: dict[str, list[str] | str] = {}
        for venv_path in venvs:
            try:
                dependencies = freeze_requirements(venv_path)
                write_requirements(
                    venv_path,
                    dependencies,
                    _recursive_output_dir(venv_path) / OUTPUT_FILENAME,
                )
            except FreezenvError as error:
                results[str(venv_path)] = f"Error: {error}"
            else:
                results[str(venv_path)] = dependencies

        return results

    try:
        dependencies = freeze_requirements(path)
        write_requirements(path, dependencies)
    except FreezenvError as error:
        return f"Error: {error}"

    return dependencies


def _write_metadata(site_packages: str, folder: str, name: str, version: str) -> None:
    """Create a minimal ``.dist-info/METADATA`` file for self-tests."""
    dist_info = os.path.join(site_packages, folder)
    os.makedirs(dist_info)

    with open(os.path.join(dist_info, "METADATA"), "w", encoding="utf-8") as f:
        f.write(f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n")


def _run_tests() -> bool:
    """Run focused, dependency-free checks for the script's core behavior.

    These tests build temporary fake virtual environments instead of creating
    real venvs or invoking ``pip``. They verify discovery, metadata parsing,
    filtering, sorting, duplicate removal, output writing, and error handling.
    """
    with tempfile.TemporaryDirectory() as tmp:
        project = os.path.join(tmp, "project")
        site_packages = os.path.join(project, ".venv", "lib", "python3.12", "site-packages")
        os.makedirs(site_packages)
        with open(os.path.join(project, ".venv", "pyvenv.cfg"), "w", encoding="utf-8") as f:
            f.write("home = /usr/bin\n")

        _write_metadata(site_packages, "Zebra-1.0.dist-info", "Zebra", "1.0")
        _write_metadata(site_packages, "alpha-2.0.dist-info", "alpha", "2.0")
        _write_metadata(site_packages, "pip-24.0.dist-info", "pip", "24.0")
        _write_metadata(site_packages, "alpha-copy.dist-info", "alpha", "2.0")

        result = freeze_venv(project)
        expected = ["alpha==2.0", "Zebra==1.0"]
        assert result == expected, f"expected {expected!r}, got {result!r}"

        output_file = os.path.join(project, OUTPUT_FILENAME)
        with open(output_file, "r", encoding="utf-8") as f:
            assert f.read() == "alpha==2.0\nZebra==1.0"

    with tempfile.TemporaryDirectory() as tmp:
        direct_venv = os.path.join(tmp, "direct")
        site_packages = os.path.join(direct_venv, "Lib", "site-packages")
        os.makedirs(site_packages)
        with open(os.path.join(direct_venv, "pyvenv.cfg"), "w", encoding="utf-8") as f:
            f.write("home = C:\\Python\n")

        _write_metadata(site_packages, "requests-2.32.0.dist-info", "requests", "2.32.0")
        assert freeze_venv(direct_venv) == ["requests==2.32.0"]

    with tempfile.TemporaryDirectory() as tmp:
        result = freeze_venv(tmp)
        assert isinstance(result, str)
        assert result.startswith("Error: No virtual environment")

    with tempfile.TemporaryDirectory() as tmp:
        venv = os.path.join(tmp, "venv")
        os.makedirs(venv)
        with open(os.path.join(venv, "pyvenv.cfg"), "w", encoding="utf-8") as f:
            f.write("home = /usr/bin\n")

        assert freeze_venv(tmp) == "Error: Could not locate site-packages directory."

    with tempfile.TemporaryDirectory() as tmp:
        project_a = os.path.join(tmp, "project-a")
        project_b = os.path.join(tmp, "project-b")
        custom_venv = os.path.join(tmp, "custom-env")
        site_a = os.path.join(project_a, ".venv", "lib", "python3.12", "site-packages")
        site_b = os.path.join(project_b, "venv", "lib", "python3.12", "site-packages")
        site_custom = os.path.join(custom_venv, "Lib", "site-packages")

        for venv_path, site_packages in (
            (os.path.join(project_a, ".venv"), site_a),
            (os.path.join(project_b, "venv"), site_b),
            (custom_venv, site_custom),
        ):
            os.makedirs(site_packages)
            with open(os.path.join(venv_path, "pyvenv.cfg"), "w", encoding="utf-8") as f:
                f.write("home = /usr/bin\n")

        _write_metadata(site_a, "alpha-1.0.dist-info", "alpha", "1.0")
        _write_metadata(site_b, "bravo-2.0.dist-info", "bravo", "2.0")
        _write_metadata(site_custom, "charlie-3.0.dist-info", "charlie", "3.0")

        result = freeze_venv(tmp, recursive=True)
        expected = {
            os.path.join(project_a, ".venv"): ["alpha==1.0"],
            os.path.join(project_b, "venv"): ["bravo==2.0"],
            custom_venv: ["charlie==3.0"],
        }
        assert result == expected, f"expected {expected!r}, got {result!r}"

        expected_outputs = (
            (project_a, "alpha==1.0"),
            (project_b, "bravo==2.0"),
            (custom_venv, "charlie==3.0"),
        )
        for output_dir, expected_contents in expected_outputs:
            output_file = os.path.join(output_dir, OUTPUT_FILENAME)
            with open(output_file, "r", encoding="utf-8") as f:
                assert f.read() == expected_contents

    with tempfile.TemporaryDirectory() as tmp:
        result = freeze_venv(tmp, recursive=True)
        expected = {tmp: "Error: No virtual environments found under the provided path."}
        assert result == expected, f"expected {expected!r}, got {result!r}"

    return True


def _build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for ``freezenv``."""
    parser = argparse.ArgumentParser(
        prog="freezenv",
        description=(
            "Generate auto_requirements.txt from an existing virtual environment "
            "without invoking pip."
        ),
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="directory containing a venv, venv/, or .venv/ (default: current directory)",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="scan recursively and freeze every virtual environment found",
    )
    parser.add_argument(
        "-t",
        "--tests",
        action="store_true",
        help="run the built-in self-tests and exit",
    )
    return parser


def _main(argv: list[str] | None = None) -> int:
    """Run the ``freezenv`` command-line interface."""
    args = _build_parser().parse_args(argv)

    if args.tests:
        try:
            _run_tests()
        except AssertionError as exc:
            print(f"Self-tests failed: {exc}", file=sys.stderr)
            return 1

        print("Self-tests passed.")
        return 0

    result = freeze_venv(args.path, recursive=args.recursive)
    if isinstance(result, str):
        print(result, file=sys.stderr)
        return 1

    if isinstance(result, dict):
        exit_code = 0
        for venv_path, dependencies in result.items():
            if isinstance(dependencies, str):
                print(f"{venv_path}: {dependencies}", file=sys.stderr)
                exit_code = 1
                continue

            output_file = _recursive_output_dir(Path(venv_path)) / OUTPUT_FILENAME
            print(f"Wrote {len(dependencies)} dependencies to {output_file}")

        return exit_code

    output_file = os.path.join(args.path, OUTPUT_FILENAME)
    print(f"Wrote {len(result)} dependencies to {output_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
