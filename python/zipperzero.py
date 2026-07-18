# CODEPILLS-META-BEGIN
# schema: codepills.tool/v1
# name: zipper-zero
# version: 1.0.0
# author: octanima-labs
# description: List, test, extract, and create ZIP and TAR archives using the Python standard library.
# repo: https://github.com/octanima-labs/codepills/blob/main/python/zipperzero.py
# license: MIT
# usage: python python/zipperzero.py SOURCE [OPTIONS]
# tags:
#   - python
#   - cli
#   - zip
#   - tar
# requires:
#   - Python standard library
# platforms:
#   - Linux
#   - macOS
#   - Windows
# CODEPILLS-META-END

"""Zipper-Zero: a standard-library-only ZIP/TAR CLI and helper."""

import argparse
import io
import shutil
import sys
import tarfile
import unittest
import zlib
from contextlib import redirect_stderr, redirect_stdout
from tempfile import TemporaryDirectory
from unittest.mock import patch
from pathlib import Path, PurePosixPath, PureWindowsPath
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, is_zipfile


def _safe_member_name(name: str) -> bool:
    """Return True when an archive member path is safe to extract."""
    if not name or "\x00" in name:
        return False

    posix_path = PurePosixPath(name)
    windows_path = PureWindowsPath(name)
    if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        return False

    return ".." not in posix_path.parts and ".." not in windows_path.parts


def _archive_format_for_existing(path: Path) -> str:
    """Detect the archive format for an existing archive path."""
    if not path.exists():
        raise FileNotFoundError(path)
    if is_zipfile(path):
        return "zip"
    if tarfile.is_tarfile(path):
        return "tar"
    raise ValueError(f"Unsupported archive format: {path}")


def _archive_format_for_output(path: Path) -> str:
    """Return the archive format implied by an output path."""
    suffixes = [suffix.lower() for suffix in path.suffixes]
    if suffixes[-2:] == [".tar", ".gz"] or path.suffix.lower() == ".tgz":
        return "tar.gz"
    if path.suffix.lower() == ".tar":
        return "tar"
    return "zip"


def _default_extract_destination(path: Path) -> Path:
    """Return the default extraction directory for an archive path."""
    suffixes = [suffix.lower() for suffix in path.suffixes]
    if suffixes[-2:] == [".tar", ".gz"]:
        return path.with_suffix("").with_suffix("")
    return path.with_suffix("")


def _merge_extracted_tree(staged: Path, destination: Path):
    """Merge staged extraction output, preserving unrelated destination files."""
    destination.mkdir(parents=True, exist_ok=True)

    for item in staged.iterdir():
        target = destination / item.name
        if item.is_dir():
            if target.exists() and not target.is_dir():
                print(f"Skipping directory over file conflict: {target}", file=sys.stderr)
                continue
            _merge_extracted_tree(item, target)
        elif item.is_file():
            if target.exists() and target.is_dir():
                print(f"Skipping file over directory conflict: {target}", file=sys.stderr)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                target.unlink()
            shutil.move(str(item), str(target))


def _compress_level(value: str) -> int:
    """Parse a compression level accepted by supported compressed formats."""
    try:
        level = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer from 0 to 9") from error

    if not 0 <= level <= 9:
        raise argparse.ArgumentTypeError("must be an integer from 0 to 9")
    return level


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="zz",
        description="Zipper-Zero lists, tests, extracts, and creates ZIP and TAR archives.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  zz archive.zip\n"
            "  zz --test archive.zip\n"
            "  zz --extract archive.zip -o out_dir\n"
            "  zz --extract archive.zip -o out_dir --force\n"
            "  zz --create source_dir --compress-level 9\n"
            "  zz --create source_dir -o archive.tar.gz\n"
            "  zipper-zero --self-test"
        ),
    )
    parser.add_argument(
        "source_path",
        metavar="SOURCE",
        nargs="?",
        type=Path,
        help="ZIP/TAR archive for list/test/extract, or file/directory for --create.",
    )
    parser.add_argument(
        "-o", "--output",
        metavar="OUT_PATH",
        type=Path,
        help=(
            "Output archive path for --create or destination directory for --extract. "
            "Defaults to a sibling .zip for create and archive-stem/ for extract."
        ),
    )
    parser.add_argument(
        "-f", "--force",
        action="store_true",
        default=False,
        help=(
            "For --create, replace an existing output archive. For --extract, merge into "
            "a non-empty destination and overwrite matching files."
        ),
    )
    parser.add_argument(
        "--compress-level",
        metavar="LEVEL",
        type=_compress_level,
        help=(
            "Compression level for --create ZIP/TAR.GZ output: "
            "0 (fastest) through 9 (smallest)."
        ),
    )
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "-l", "--list",
        dest="mode",
        action="store_const",
        const="list",
        help="List one archive member per line. This is the default mode.",
    )
    modes.add_argument(
        "-x", "--extract",
        dest="mode",
        action="store_const",
        const="extract",
        help="Safely extract a ZIP/TAR archive to a directory.",
    )
    modes.add_argument(
        "-c", "--create",
        dest="mode",
        action="store_const",
        const="create",
        help="Create a ZIP/TAR archive from a file or directory SOURCE.",
    )
    modes.add_argument(
        "-t", "--test",
        dest="mode",
        action="store_const",
        const="test",
        help="Test archive integrity and fail if a corrupt member is found.",
    )
    parser.add_argument(
        "-T", "--self-test",
        action="store_true",
        default=False,
        help="Run the built-in standard-library self-test suite and exit.",
    )
    parser.set_defaults(mode="list")
    return parser


def _parse_args(cmd=None):
    """Parse command-line arguments."""
    parser = _build_parser()
    return parser.parse_args(cmd)


def _validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace):
    """Apply mode-specific validation that argparse cannot express directly."""
    if args.self_test:
        return
    if args.source_path is None:
        parser.error("SOURCE is required unless --self-test is used")
    if args.mode not in {"create", "extract"}:
        if args.output is not None:
            parser.error("-o/--output can only be used with --create or --extract")
        if args.force:
            parser.error("--force can only be used with --create or --extract")
    if args.compress_level is not None and args.mode != "create":
        parser.error("--compress-level can only be used with --create")


class ZipperZero:
    """Project-facing helper for archive operations.

    Instantiate `ZipperZero(path)` for existing ZIP/TAR archives and use it as a
    context manager or call `close()` when finished. Use `ZipperZero.create()`
    to create archives; it returns the output `Path`.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.format = _archive_format_for_existing(self.path)
        if self.format == "zip":
            self.archive = ZipFile(self.path)
        else:
            self.archive = tarfile.open(self.path, "r:*")

    def close(self):
        """Close the underlying archive handle."""
        self.archive.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False

    def contents(self, detailed: bool = False):
        """Return archive member names, or member info objects when detailed."""
        if self.format == "zip":
            return self.archive.infolist() if detailed else self.archive.namelist()
        return self.archive.getmembers() if detailed else self.archive.getnames()

    def test(self):
        """Return the first corrupt member name, or `None` when the archive is OK."""
        if self.format == "zip":
            return self.archive.testzip()

        current_name = "<archive>"
        try:
            for member in self.archive.getmembers():
                current_name = member.name
                if not member.isfile():
                    continue
                extracted = self.archive.extractfile(member)
                if extracted is None:
                    return member.name
                with extracted:
                    while extracted.read(1024 * 1024):
                        pass
        except (tarfile.TarError, OSError, EOFError, zlib.error):
            return current_name
        return None

    def _safe_tar_members(self, destination: Path, members=None):
        """Return TAR members that are safe to extract."""
        if members is None:
            requested = None
        else:
            requested = {
                member.name if hasattr(member, "name") else str(member)
                for member in members
            }

        safe_members = []
        for member in self.archive.getmembers():
            if requested is not None and member.name not in requested:
                continue
            if not _safe_member_name(member.name):
                raise ValueError(f"Unsafe TAR member path: {member.name!r}")

            target = (destination / member.name).resolve()
            if target != destination and destination not in target.parents:
                raise ValueError(f"Unsafe TAR member path: {member.name!r}")

            if member.issym() or member.islnk():
                print(f"Skipping TAR link member: {member.name}", file=sys.stderr)
                continue
            if not member.isfile() and not member.isdir():
                print(f"Skipping unsupported TAR member: {member.name}", file=sys.stderr)
                continue

            safe_members.append(member)
        return safe_members

    def extractall(self, path: str | Path | None = None, members=None, pwd=None, force: bool = False):
        """Extract safely and return the final destination directory.

        Unsafe member paths are rejected before writing. Extraction is staged in
        a temporary directory, then merged into the destination. Non-empty
        destinations require `force=True`.
        """
        destination = (
            Path(path) if path not in [None, ""] else _default_extract_destination(self.path)
        )
        destination = destination.resolve()

        if self.format == "zip":
            for member in self.archive.infolist():
                if not _safe_member_name(member.filename):
                    raise ValueError(f"Unsafe ZIP member path: {member.filename!r}")

                target = (destination / member.filename).resolve()
                if target != destination and destination not in target.parents:
                    raise ValueError(f"Unsafe ZIP member path: {member.filename!r}")
        else:
            members = self._safe_tar_members(destination, members=members)

        if destination.exists():
            if not destination.is_dir():
                raise ValueError(f"Extraction destination is not a directory: {destination}")
            if not force and any(destination.iterdir()):
                raise ValueError(f"Extraction destination is not empty: {destination}")

        destination.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=destination.parent) as tmpdir:
            staged = Path(tmpdir)
            if self.format == "zip":
                self.archive.extractall(staged, members=members, pwd=pwd)
            else:
                self.archive.extractall(staged, members=members)
            _merge_extracted_tree(staged, destination)

        return destination

    @staticmethod
    def default_output(source: Path) -> Path:
        """Return the default output archive path for a source file or directory."""
        if source.is_dir():
            return source.parent / f"{source.name}.zip"
        return source.with_suffix(".zip")

    @classmethod
    def create(
        cls,
        source_path: str | Path,
        output_path: str | Path | None = None,
        force: bool = False,
        compress_level: int | None = None,
    ) -> Path:
        """Create a ZIP/TAR archive from a file or directory and return its path.

        Directory creation preserves empty directories, includes hidden paths,
        and skips symlinks. Existing output archive files require `force=True`.
        """
        if compress_level is not None and not 0 <= compress_level <= 9:
            raise ValueError("Compression level must be an integer from 0 to 9")

        source = Path(source_path)
        if not source.exists():
            raise FileNotFoundError(source)
        if source.is_symlink():
            raise ValueError("SOURCE symlinks are not supported")

        output = Path(output_path) if output_path not in [None, ""] else cls.default_output(source)
        output_format = _archive_format_for_output(output)
        if compress_level is not None and output_format == "tar":
            raise ValueError("Compression level only applies to ZIP and TAR.GZ output")
        output.parent.mkdir(parents=True, exist_ok=True)

        source_resolved = source.resolve()
        output_resolved = output.resolve()
        if source_resolved == output_resolved:
            raise ValueError("Output path must be different from SOURCE")
        if output.exists():
            if output.is_dir():
                raise ValueError(f"Output path is a directory: {output}")
            if not force:
                raise ValueError(f"Output file already exists: {output}")

        if output_format in {"tar", "tar.gz"}:
            mode = "w:gz" if output_format == "tar.gz" else "w"
            open_kwargs = (
                {"compresslevel": compress_level}
                if output_format == "tar.gz" and compress_level is not None
                else {}
            )
            with tarfile.open(output, mode, **open_kwargs) as archive:
                if source.is_file():
                    archive.add(source, arcname=source.name, recursive=False)
                    return output

                for path in sorted(source.rglob("*")):
                    if path.resolve() == output_resolved:
                        continue
                    if path.is_symlink():
                        continue

                    relative_path = path.relative_to(source).as_posix()
                    if path.is_dir():
                        if not any(path.iterdir()):
                            archive.add(path, arcname=relative_path, recursive=False)
                    elif path.is_file():
                        archive.add(path, arcname=relative_path, recursive=False)

            return output

        with ZipFile(output, "w", compression=ZIP_DEFLATED, compresslevel=compress_level) as archive:
            if source.is_file():
                archive.write(source, source.name)
                return output

            for path in sorted(source.rglob("*")):
                if path.resolve() == output_resolved:
                    continue
                if path.is_symlink():
                    continue

                relative_path = path.relative_to(source)
                if path.is_dir():
                    if not any(path.iterdir()):
                        archive.write(path, f"{relative_path}/")
                elif path.is_file():
                    archive.write(path, relative_path)

        return output


def run_mode(
    mode: str,
    source_path: Path,
    output_path: Path | None = None,
    force: bool = False,
    compress_level: int | None = None,
) -> Path | None:
    """Run the selected CLI mode and print human-readable output."""
    if mode == "create":
        output = ZipperZero.create(source_path, output_path, force=force, compress_level=compress_level)
        print(f"Created {output}")
        return output

    with ZipperZero(source_path) as zfile:
        if mode == "test":
            failed_member = zfile.test()
            if failed_member is None:
                print("Verification OK")
            else:
                raise ValueError(f"Verification failed. First corrupted member: {failed_member}")
        elif mode == "list":
            for member in zfile.contents():
                print(member)
        elif mode == "extract":
            destination = zfile.extractall(output_path, force=force)
            print(f"Extracted to {destination}")
        else:
            raise ValueError(f"Unknown mode: {mode}")

    return None


class ZipperZeroSelfTests(unittest.TestCase):
    """Built-in tests for core archive create, inspect, and extract behavior."""

    def test_create_directory_uses_default_sibling_zip(self):
        with TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "source"
            (source / "nested").mkdir(parents=True)
            (source / "hello.txt").write_text("hello\n")
            (source / "nested" / "deep.txt").write_text("deep\n")

            output = ZipperZero.create(source)

            self.assertEqual(output, source.parent / "source.zip")
            with ZipperZero(output) as archive:
                self.assertEqual(archive.test(), None)
                self.assertEqual(sorted(archive.contents()), ["hello.txt", "nested/deep.txt"])

    def test_create_file_uses_default_replaced_suffix(self):
        with TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "note.txt"
            source.write_text("hello\n")

            output = ZipperZero.create(source)

            self.assertIsInstance(output, Path)
            self.assertEqual(output, source.with_suffix(".zip"))
            with ZipperZero(output) as archive:
                self.assertEqual(archive.contents(), ["note.txt"])

    def test_create_refuses_existing_output_without_force(self):
        with TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "source"
            source.mkdir()
            (source / "hello.txt").write_text("hello\n")
            output = Path(tmpdir) / "out.zip"
            output.write_text("old content")

            with self.assertRaises(ValueError):
                ZipperZero.create(source, output)

            self.assertEqual(output.read_text(), "old content")

    def test_create_replaces_existing_output_with_force(self):
        with TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "source"
            source.mkdir()
            (source / "hello.txt").write_text("hello\n")
            output = Path(tmpdir) / "out.zip"
            output.write_text("old content")

            ZipperZero.create(source, output, force=True)

            with ZipperZero(output) as archive:
                self.assertEqual(archive.contents(), ["hello.txt"])

    def test_create_skips_symlinked_paths(self):
        with TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "source"
            real_dir = source / "real-dir"
            real_dir.mkdir(parents=True)
            (source / "real.txt").write_text("real\n")
            (real_dir / "nested.txt").write_text("nested\n")

            try:
                (source / "file-link.txt").symlink_to(source / "real.txt")
                (source / "dir-link").symlink_to(real_dir, target_is_directory=True)
            except OSError as error:
                self.skipTest(f"Symlinks are unavailable: {error}")

            output = ZipperZero.create(source)

            with ZipperZero(output) as archive:
                self.assertEqual(sorted(archive.contents()), ["real-dir/nested.txt", "real.txt"])

    def test_create_preserves_empty_directories(self):
        with TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "source"
            (source / "empty").mkdir(parents=True)

            output = ZipperZero.create(source)

            with ZipperZero(output) as archive:
                self.assertEqual(archive.contents(), ["empty/"])

    def test_create_includes_hidden_paths(self):
        with TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "source"
            (source / ".hidden-dir").mkdir(parents=True)
            (source / ".hidden").write_text("hidden\n")
            (source / ".hidden-dir" / "file.txt").write_text("nested\n")

            output = ZipperZero.create(source)

            with ZipperZero(output) as archive:
                self.assertEqual(sorted(archive.contents()), [".hidden", ".hidden-dir/file.txt"])

    def test_create_accepts_compression_level(self):
        with TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "source"
            source.mkdir()
            (source / "hello.txt").write_text("hello\n")

            output = ZipperZero.create(source, compress_level=9)

            self.assertIsInstance(output, Path)
            with ZipperZero(output) as archive:
                self.assertEqual(archive.contents(), ["hello.txt"])

    def test_create_rejects_invalid_compression_level(self):
        with TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "source"
            source.mkdir()

            with self.assertRaises(ValueError):
                ZipperZero.create(source, compress_level=10)

    def test_create_tar_archive_from_directory(self):
        with TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "source"
            (source / "nested").mkdir(parents=True)
            (source / "hello.txt").write_text("hello\n")
            (source / "nested" / "deep.txt").write_text("deep\n")
            output = Path(tmpdir) / "out.tar"

            ZipperZero.create(source, output)

            with ZipperZero(output) as archive:
                self.assertEqual(archive.test(), None)
                self.assertEqual(sorted(archive.contents()), ["hello.txt", "nested/deep.txt"])

    def test_create_tar_gz_archive_from_directory(self):
        with TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "source"
            source.mkdir()
            (source / "hello.txt").write_text("hello\n")
            output = Path(tmpdir) / "out.tar.gz"

            ZipperZero.create(source, output, compress_level=9)

            with ZipperZero(output) as archive:
                self.assertEqual(archive.test(), None)
                self.assertEqual(archive.contents(), ["hello.txt"])

    def test_create_rejects_compression_level_for_plain_tar(self):
        with TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "source"
            source.mkdir()
            output = Path(tmpdir) / "out.tar"

            with self.assertRaises(ValueError):
                ZipperZero.create(source, output, compress_level=9)

    def test_extract_defaults_to_archive_stem_directory(self):
        with TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / "archive.zip"
            with ZipFile(archive_path, "w") as archive:
                archive.writestr("hello.txt", "hello\n")

            with ZipperZero(archive_path) as archive:
                destination = archive.extractall()

            self.assertEqual(destination, archive_path.with_suffix("").resolve())
            self.assertEqual((destination / "hello.txt").read_text(), "hello\n")

    def test_extract_accepts_explicit_output_directory(self):
        with TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "source"
            source.mkdir()
            (source / "hello.txt").write_text("hello\n")
            archive_path = ZipperZero.create(source)
            output = Path(tmpdir) / "out"

            with ZipperZero(archive_path) as archive:
                destination = archive.extractall(output)

            self.assertEqual(destination, output.resolve())
            self.assertEqual((output / "hello.txt").read_text(), "hello\n")

    def test_extract_tar_archive(self):
        with TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "source"
            source.mkdir()
            (source / "hello.txt").write_text("hello\n")
            archive_path = ZipperZero.create(source, Path(tmpdir) / "archive.tar")
            output = Path(tmpdir) / "out"

            with ZipperZero(archive_path) as archive:
                destination = archive.extractall(output)

            self.assertEqual(destination, output.resolve())
            self.assertEqual((output / "hello.txt").read_text(), "hello\n")

    def test_extract_tar_gz_defaults_to_archive_stem_directory(self):
        with TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "source"
            source.mkdir()
            (source / "hello.txt").write_text("hello\n")
            archive_path = ZipperZero.create(source, Path(tmpdir) / "archive.tar.gz")

            with ZipperZero(archive_path) as archive:
                destination = archive.extractall()

            self.assertEqual(destination, (Path(tmpdir) / "archive").resolve())
            self.assertEqual((destination / "hello.txt").read_text(), "hello\n")

    def test_extract_refuses_non_empty_destination_without_force(self):
        with TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "source"
            source.mkdir()
            (source / "hello.txt").write_text("hello\n")
            archive_path = ZipperZero.create(source)
            output = Path(tmpdir) / "out"
            output.mkdir()
            (output / "existing.txt").write_text("keep\n")

            with self.assertRaises(ValueError):
                with ZipperZero(archive_path) as archive:
                    archive.extractall(output)

            self.assertFalse((output / "hello.txt").exists())
            self.assertEqual((output / "existing.txt").read_text(), "keep\n")

    def test_extract_allows_non_empty_destination_with_force(self):
        with TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "source"
            source.mkdir()
            (source / "hello.txt").write_text("hello\n")
            archive_path = ZipperZero.create(source)
            output = Path(tmpdir) / "out"
            output.mkdir()
            (output / "existing.txt").write_text("keep\n")
            (output / "hello.txt").write_text("old\n")

            with ZipperZero(archive_path) as archive:
                archive.extractall(output, force=True)

            self.assertEqual((output / "hello.txt").read_text(), "hello\n")
            self.assertEqual((output / "existing.txt").read_text(), "keep\n")

    def test_extract_skips_file_over_directory_conflict_with_warning(self):
        with TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / "archive.zip"
            with ZipFile(archive_path, "w") as archive:
                archive.writestr("conflict", "archive file\n")
            output = Path(tmpdir) / "out"
            (output / "conflict").mkdir(parents=True)
            (output / "conflict" / "existing.txt").write_text("keep\n")
            stderr = io.StringIO()

            with ZipperZero(archive_path) as archive, redirect_stderr(stderr):
                archive.extractall(output, force=True)

            self.assertIn("Skipping file over directory conflict", stderr.getvalue())
            self.assertTrue((output / "conflict").is_dir())
            self.assertEqual((output / "conflict" / "existing.txt").read_text(), "keep\n")

    def test_extract_skips_directory_over_file_conflict_with_warning(self):
        with TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / "archive.zip"
            with ZipFile(archive_path, "w") as archive:
                archive.writestr("conflict/nested.txt", "archive file\n")
            output = Path(tmpdir) / "out"
            output.mkdir()
            (output / "conflict").write_text("keep\n")
            stderr = io.StringIO()

            with ZipperZero(archive_path) as archive, redirect_stderr(stderr):
                archive.extractall(output, force=True)

            self.assertIn("Skipping directory over file conflict", stderr.getvalue())
            self.assertEqual((output / "conflict").read_text(), "keep\n")
            self.assertFalse((output / "conflict" / "nested.txt").exists())

    def test_extract_rejects_unsafe_member_before_writing_files(self):
        with TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / "bad.zip"
            destination = Path(tmpdir) / "out"
            with ZipFile(archive_path, "w") as archive:
                archive.writestr("ok.txt", "ok")
                archive.writestr("../evil.txt", "bad")

            with self.assertRaises(ValueError):
                with ZipperZero(archive_path) as archive:
                    archive.extractall(destination)

            self.assertFalse((destination / "ok.txt").exists())
            self.assertFalse((Path(tmpdir) / "evil.txt").exists())

    def test_extract_tar_rejects_unsafe_member_before_writing_files(self):
        with TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / "bad.tar"
            destination = Path(tmpdir) / "out"
            with tarfile.open(archive_path, "w") as archive:
                ok_data = b"ok"
                ok_member = tarfile.TarInfo("ok.txt")
                ok_member.size = len(ok_data)
                archive.addfile(ok_member, io.BytesIO(ok_data))
                bad_data = b"bad"
                bad_member = tarfile.TarInfo("../evil.txt")
                bad_member.size = len(bad_data)
                archive.addfile(bad_member, io.BytesIO(bad_data))

            with self.assertRaises(ValueError):
                with ZipperZero(archive_path) as archive:
                    archive.extractall(destination)

            self.assertFalse((destination / "ok.txt").exists())
            self.assertFalse((Path(tmpdir) / "evil.txt").exists())

    def test_extract_tar_skips_links_with_warning(self):
        with TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / "links.tar"
            output = Path(tmpdir) / "out"
            with tarfile.open(archive_path, "w") as archive:
                data = b"hello\n"
                member = tarfile.TarInfo("hello.txt")
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))
                link = tarfile.TarInfo("link.txt")
                link.type = tarfile.SYMTYPE
                link.linkname = "hello.txt"
                archive.addfile(link)
            stderr = io.StringIO()

            with ZipperZero(archive_path) as archive, redirect_stderr(stderr):
                archive.extractall(output)

            self.assertEqual((output / "hello.txt").read_text(), "hello\n")
            self.assertFalse((output / "link.txt").exists())
            self.assertIn("Skipping TAR link member: link.txt", stderr.getvalue())

    def test_extract_tar_skips_special_members_with_warning(self):
        with TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / "special.tar"
            output = Path(tmpdir) / "out"
            with tarfile.open(archive_path, "w") as archive:
                fifo = tarfile.TarInfo("named-pipe")
                fifo.type = tarfile.FIFOTYPE
                archive.addfile(fifo)
            stderr = io.StringIO()

            with ZipperZero(archive_path) as archive, redirect_stderr(stderr):
                archive.extractall(output)

            self.assertFalse((output / "named-pipe").exists())
            self.assertIn("Skipping unsupported TAR member: named-pipe", stderr.getvalue())

    def test_self_test_flag_does_not_require_source(self):
        args = _parse_args(["--self-test"])

        self.assertTrue(args.self_test)
        self.assertIsNone(args.source_path)

    def test_force_flag_parses(self):
        args = _parse_args(["--create", "--force", "source"])

        self.assertTrue(args.force)
        self.assertEqual(args.mode, "create")

    def test_compress_level_flag_parses(self):
        args = _parse_args(["--create", "--compress-level", "3", "source"])

        self.assertEqual(args.compress_level, 3)

    def test_invalid_compress_level_uses_argparse_error(self):
        stderr = io.StringIO()

        with redirect_stderr(stderr), self.assertRaises(SystemExit) as error:
            _parse_args(["--create", "--compress-level", "10", "source"])

        self.assertEqual(error.exception.code, 2)
        self.assertIn("must be an integer from 0 to 9", stderr.getvalue())

    def test_compress_level_requires_create_mode(self):
        with TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / "archive.zip"
            with ZipFile(archive_path, "w") as archive:
                archive.writestr("hello.txt", "hello\n")
            stderr = io.StringIO()

            with redirect_stderr(stderr), self.assertRaises(SystemExit) as error:
                main(["--compress-level", "1", str(archive_path)])

            self.assertEqual(error.exception.code, 2)
            self.assertIn("--compress-level can only be used with --create", stderr.getvalue())

    def test_output_flag_rejected_for_list_mode(self):
        with TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / "archive.zip"
            with ZipFile(archive_path, "w") as archive:
                archive.writestr("hello.txt", "hello\n")
            stderr = io.StringIO()

            with redirect_stderr(stderr), self.assertRaises(SystemExit) as error:
                main(["--list", "-o", "out", str(archive_path)])

            self.assertEqual(error.exception.code, 2)
            self.assertIn("-o/--output can only be used with --create or --extract", stderr.getvalue())

    def test_output_flag_rejected_for_test_mode(self):
        with TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / "archive.zip"
            with ZipFile(archive_path, "w") as archive:
                archive.writestr("hello.txt", "hello\n")
            stderr = io.StringIO()

            with redirect_stderr(stderr), self.assertRaises(SystemExit) as error:
                main(["--test", "-o", "out", str(archive_path)])

            self.assertEqual(error.exception.code, 2)
            self.assertIn("-o/--output can only be used with --create or --extract", stderr.getvalue())

    def test_force_flag_rejected_for_list_mode(self):
        with TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / "archive.zip"
            with ZipFile(archive_path, "w") as archive:
                archive.writestr("hello.txt", "hello\n")
            stderr = io.StringIO()

            with redirect_stderr(stderr), self.assertRaises(SystemExit) as error:
                main(["--list", "--force", str(archive_path)])

            self.assertEqual(error.exception.code, 2)
            self.assertIn("--force can only be used with --create or --extract", stderr.getvalue())

    def test_force_flag_rejected_for_test_mode(self):
        with TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / "archive.zip"
            with ZipFile(archive_path, "w") as archive:
                archive.writestr("hello.txt", "hello\n")
            stderr = io.StringIO()

            with redirect_stderr(stderr), self.assertRaises(SystemExit) as error:
                main(["--test", "--force", str(archive_path)])

            self.assertEqual(error.exception.code, 2)
            self.assertIn("--force can only be used with --create or --extract", stderr.getvalue())

    def test_output_and_force_allowed_for_create_mode(self):
        with TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "source"
            source.mkdir()
            (source / "hello.txt").write_text("hello\n")
            output = Path(tmpdir) / "out.zip"
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = main(["--create", "--force", "-o", str(output), str(source)])

            self.assertEqual(exit_code, 0)
            self.assertTrue(output.exists())

    def test_output_and_force_allowed_for_extract_mode(self):
        with TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / "archive.zip"
            with ZipFile(archive_path, "w") as archive:
                archive.writestr("hello.txt", "hello\n")
            output = Path(tmpdir) / "out"
            stdout = io.StringIO()

            with redirect_stdout(stdout):
                exit_code = main(["--extract", "--force", "-o", str(output), str(archive_path)])

            self.assertEqual(exit_code, 0)
            self.assertEqual((output / "hello.txt").read_text(), "hello\n")

    def test_missing_source_uses_argparse_error(self):
        stderr = io.StringIO()

        with redirect_stderr(stderr), self.assertRaises(SystemExit) as error:
            main([])

        self.assertEqual(error.exception.code, 2)
        self.assertIn("error:", stderr.getvalue())
        self.assertIn("SOURCE is required", stderr.getvalue())

    def test_cli_errors_are_written_to_stderr(self):
        stderr = io.StringIO()

        with redirect_stderr(stderr):
            exit_code = main(["--create", "missing"])

        self.assertEqual(exit_code, 1)
        self.assertIn("Path does not exist", stderr.getvalue())

    def test_integrity_failure_returns_non_zero(self):
        with TemporaryDirectory() as tmpdir:
            archive_path = Path(tmpdir) / "archive.zip"
            with ZipFile(archive_path, "w") as archive:
                archive.writestr("bad.txt", "content")
            stderr = io.StringIO()

            with patch.object(ZipperZero, "test", return_value="bad.txt"), redirect_stderr(stderr):
                exit_code = main(["--test", str(archive_path)])

            self.assertEqual(exit_code, 1)
            self.assertIn("bad.txt", stderr.getvalue())


def _run_self_tests() -> int:
    """Run built-in tests and return a process-style exit code."""
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ZipperZeroSelfTests)
    if suite.countTestCases() == 0:
        print("No self-tests found")
        return 1

    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


def main(cmd=None) -> int:
    """CLI entrypoint returning a process-style exit code."""
    parser = _build_parser()
    args = parser.parse_args(cmd)
    _validate_args(parser, args)
    if args.self_test:
        return _run_self_tests()

    try:
        run_mode(
            args.mode,
            args.source_path,
            args.output,
            force=args.force,
            compress_level=args.compress_level,
        )
    except FileNotFoundError:
        print(f"Path does not exist: {args.source_path}", file=sys.stderr)
        return 1
    except BadZipFile:
        print(f"Not a valid ZIP file: {args.source_path}", file=sys.stderr)
        return 1
    except tarfile.TarError:
        print(f"Not a valid TAR file: {args.source_path}", file=sys.stderr)
        return 1
    except ValueError as error:
        print(error, file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
