"""Generate a requirements file from an existing Python virtual environment.

``freezenv`` is a small, dependency-free alternative to running ``pip freeze``
inside a virtual environment. It scans package metadata from a venv located at
the provided path, ``venv`` subdirectory, or ``.venv`` subdirectory, then writes
the discovered packages to ``auto_requirements.txt``.

Examples:
    Generate requirements for the current directory::

        python freezenv.py

    Generate requirements for a specific project directory::

        python freezenv.py /path/to/project

    Run the built-in self-tests::

        python freezenv.py --tests
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile


BASE_PACKAGES = {"pip", "setuptools", "wheel", "distribute"}
OUTPUT_FILENAME = "auto_requirements.txt"


def generate_requirements_from_venv(path: str) -> list[str] | str:
    """Create ``auto_requirements.txt`` from package metadata in a venv.

    The function looks for a virtual environment in three locations, in order:
    the provided ``path`` itself, ``path/venv``, and ``path/.venv``. Once found,
    it locates a platform-specific ``site-packages`` directory and reads each
    package's ``.dist-info/METADATA`` file to collect ``Name`` and ``Version``.

    Base packaging tools such as ``pip`` and ``setuptools`` are omitted. The
    remaining dependencies are deduplicated, sorted case-insensitively, written
    to ``auto_requirements.txt`` in the provided ``path``, and returned.

    Args:
        path: Directory containing a venv directly, or containing ``venv`` or
            ``.venv`` as a subdirectory.

    Returns:
        A sorted list of ``name==version`` requirement strings on success.
        On failure, returns an error string beginning with ``"Error:"``.
    """
    target_venv = None

    for name in ("", "venv", ".venv"):
        check_path = os.path.join(path, name)
        if os.path.exists(os.path.join(check_path, "pyvenv.cfg")):
            target_venv = check_path
            break

    if not target_venv:
        return "Error: No virtual environment found at the provided path or subdirectories."

    possible_site_paths = [
        os.path.join(target_venv, "Lib", "site-packages"),
        os.path.join(target_venv, "lib64", "site-packages"),
    ]

    lib_dir = os.path.join(target_venv, "lib")
    if os.path.exists(lib_dir):
        for item in os.listdir(lib_dir):
            if item.startswith("python"):
                possible_site_paths.append(os.path.join(lib_dir, item, "site-packages"))

    site_packages = next((p for p in possible_site_paths if os.path.exists(p)), None)

    if not site_packages:
        return "Error: Could not locate site-packages directory."

    dependencies = []

    for folder in os.listdir(site_packages):
        if not folder.endswith(".dist-info"):
            continue

        metadata_path = os.path.join(site_packages, folder, "METADATA")
        if not os.path.exists(metadata_path):
            continue

        name = None
        version = None
        with open(metadata_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("Name:"):
                    name = line.split(":", 1)[1].strip()
                elif line.startswith("Version:"):
                    version = line.split(":", 1)[1].strip()

                if name and version:
                    if name.lower() not in BASE_PACKAGES:
                        dependencies.append(f"{name}=={version}")
                    break

    dependencies = sorted(set(dependencies), key=str.lower)

    output_file = os.path.join(path, OUTPUT_FILENAME)
    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(dependencies))

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

        result = generate_requirements_from_venv(project)
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
        assert generate_requirements_from_venv(direct_venv) == ["requests==2.32.0"]

    with tempfile.TemporaryDirectory() as tmp:
        assert generate_requirements_from_venv(tmp).startswith("Error: No virtual environment")

    with tempfile.TemporaryDirectory() as tmp:
        venv = os.path.join(tmp, "venv")
        os.makedirs(venv)
        with open(os.path.join(venv, "pyvenv.cfg"), "w", encoding="utf-8") as f:
            f.write("home = /usr/bin\n")

        assert generate_requirements_from_venv(tmp) == "Error: Could not locate site-packages directory."

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

    result = generate_requirements_from_venv(args.path)
    if isinstance(result, str):
        print(result, file=sys.stderr)
        return 1

    output_file = os.path.join(args.path, OUTPUT_FILENAME)
    print(f"Wrote {len(result)} dependencies to {output_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
