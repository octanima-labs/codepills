# CODEPILLS-META-BEGIN
# schema: codepills.tool/v1
# name: massrun
# version: 1.0.0
# author: octanima-labs
# description: Run one command template for each file matched by glob patterns.
# repo: https://github.com/octanima-labs/codepills/blob/main/python/massrun.py
# license: MIT
# usage: python python/massrun.py -c "COMMAND {{TARGET}}" -t "*.png" ["*.zip" ...]
# tags:
#   - python
#   - cli
#   - batch
#   - subprocess
# requires:
#   - Python standard library
# platforms:
#   - Linux
#   - macOS
#   - Windows
# CODEPILLS-META-END

"""Run one command template for each file matched by glob patterns."""

from __future__ import annotations

import argparse
import io
import os
import shlex
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass
from pathlib import Path


PLACEHOLDERS = ("{{TARGET}}", "{{ABS}}", "{{NAME}}", "{{STEM}}", "{{EXT}}", "{{DIR}}")


@dataclass(frozen=True)
class RunResult:
    """Outcome for one target command invocation."""

    target: str
    command_display: str
    returncode: int
    stdout: str = ""
    stderr: str = ""
    launch_error: str = ""
    dry_run: bool = False

    @property
    def succeeded(self) -> bool:
        return self.returncode == 0 and not self.launch_error


def _display_args(args: list[str]) -> str:
    """Return a shell-like display string for an argv command."""

    try:
        return shlex.join(args)
    except AttributeError:
        return " ".join(shlex.quote(arg) for arg in args)


def has_placeholder(command: str) -> bool:
    """Return whether a command template contains a supported placeholder."""

    return any(placeholder in command for placeholder in PLACEHOLDERS)


def _placeholder_values(target: Path, cwd: Path) -> dict[str, str]:
    """Build placeholder values for a target path relative to the command cwd."""

    relative = target.relative_to(cwd)
    parent = relative.parent
    return {
        "{{TARGET}}": str(relative),
        "{{ABS}}": str(target.resolve()),
        "{{NAME}}": relative.name,
        "{{STEM}}": relative.stem,
        "{{EXT}}": relative.suffix,
        "{{DIR}}": "." if str(parent) == "." else str(parent),
    }


def substitute_placeholders(template: str, target: Path, cwd: Path) -> str:
    """Replace supported placeholders in a command string."""

    command = template
    for placeholder, value in _placeholder_values(target, cwd).items():
        command = command.replace(placeholder, value)
    return command


def build_argv_command(template: str, target: Path, cwd: Path) -> list[str]:
    """Build a no-shell argv command after placeholder substitution per token."""

    try:
        parts = shlex.split(template, posix=os.name != "nt")
    except ValueError as error:
        raise ValueError(f"could not parse command template: {error}") from error

    values = _placeholder_values(target, cwd)
    resolved = []
    for part in parts:
        for placeholder, value in values.items():
            part = part.replace(placeholder, value)
        resolved.append(part)
    if not resolved:
        raise ValueError("command template produced no command arguments")
    return resolved


def resolve_cwd(path: Path | None) -> Path:
    """Return a validated working directory path."""

    cwd = Path.cwd() if path is None else path.expanduser()
    if not cwd.exists():
        raise FileNotFoundError(f"working directory does not exist: {cwd}")
    if not cwd.is_dir():
        raise NotADirectoryError(f"working directory is not a directory: {cwd}")
    return cwd.resolve()


def find_targets(cwd: Path, patterns: list[str], recursive: bool = False) -> list[Path]:
    """Return deduplicated file targets matched by glob patterns under cwd."""

    targets: set[Path] = set()
    for pattern in patterns:
        matches = cwd.rglob(pattern) if recursive else cwd.glob(pattern)
        for match in matches:
            if match.is_file():
                targets.add(match.resolve())

    return sorted(targets, key=lambda path: str(path.relative_to(cwd)).lower())


def run_for_target(
    target: Path,
    cwd: Path,
    command_template: str,
    use_shell: bool = False,
    dry_run: bool = False,
) -> RunResult:
    """Run or preview one command invocation for a target."""

    target_label = str(target.relative_to(cwd))

    try:
        if use_shell:
            command = substitute_placeholders(command_template, target, cwd)
            command_display = command
        else:
            argv = build_argv_command(command_template, target, cwd)
            command = argv
            command_display = _display_args(argv)
    except ValueError as error:
        return RunResult(target=target_label, command_display=command_template, returncode=1, launch_error=str(error))

    if dry_run:
        return RunResult(target=target_label, command_display=command_display, returncode=0, dry_run=True)

    try:
        completed = subprocess.run(command, cwd=cwd, shell=use_shell, capture_output=True, text=True)
    except OSError as error:
        return RunResult(
            target=target_label,
            command_display=command_display,
            returncode=1,
            launch_error=str(error),
        )

    return RunResult(
        target=target_label,
        command_display=command_display,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def print_result(result: RunResult, quiet: bool = False, verbose: int = 0) -> None:
    """Print one target outcome according to output verbosity."""

    if result.dry_run:
        if not quiet:
            print(f"dry-run: {result.command_display}")
        return

    if not quiet:
        if result.succeeded:
            print(f"[+] {result.target}")
        elif result.launch_error:
            print(f"[!] {result.target}: {result.launch_error}")
        else:
            print(f"[!] {result.target}: exit {result.returncode}")

    if verbose:
        print(f"command: {result.command_display}")
        if result.stdout:
            print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
        if result.stderr:
            print(result.stderr, end="" if result.stderr.endswith("\n") else "\n", file=sys.stderr)


def run_batch(args: argparse.Namespace) -> int:
    """Run batch command processing and return a process exit code."""

    try:
        cwd = resolve_cwd(args.cwd)
    except OSError as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1

    if not has_placeholder(args.command):
        print("Error: command must contain at least one supported placeholder", file=sys.stderr)
        return 1

    targets = find_targets(cwd, args.targets, recursive=args.recursive)
    if not targets:
        print("Error: no targets matched", file=sys.stderr)
        return 1

    failed = False
    for target in targets:
        result = run_for_target(
            target,
            cwd,
            args.command,
            use_shell=args.shell,
            dry_run=args.dry_run,
        )
        print_result(result, quiet=args.quiet, verbose=args.verbose)
        if not result.succeeded:
            failed = True
            if args.fail_fast:
                break

    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser and detailed help text."""

    parser = argparse.ArgumentParser(
        prog="massrun",
        description="Run one command template for each file matched by glob patterns.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
behavior:
  massrun matches files with glob patterns and runs the command template once
  per target. Quote glob patterns such as "*.png" so your shell does not expand
  them before massrun sees them.

  By default, commands run without shell interpretation. This is safer for paths
  with spaces and shell metacharacters. Use --shell only when you need shell
  features such as redirects, pipes, chained commands, or shell built-ins.

placeholders:
  {{TARGET}}  target path relative to the command working directory
  {{ABS}}     absolute target path
  {{NAME}}    file name with extension
  {{STEM}}    file name without extension
  {{EXT}}     file extension, including the dot
  {{DIR}}     parent directory relative to the command working directory

working directory:
  -d/--cwd changes where target patterns are resolved and where commands run.
  It does not change the caller's shell directory.

exit codes:
  0  all commands succeeded, or --dry-run completed successfully
  1  validation error, no matched targets, command launch error, or command failed
  2  command-line usage error reported by argparse

examples:
  massrun -c "identify {{TARGET}}" -t "*.png" "*.jpg"
  massrun -d assets -c "pngquant {{TARGET}}" -t "*.png"
  massrun --dry-run -c "rm {{TARGET}}" -t "*.tmp"
  massrun --shell -c "echo {{TARGET}} >> processed.txt" -t "*.png"
  massrun -c "ffmpeg -i {{TARGET}} {{STEM}}.mp3" -t "*.wav"
  massrun -d "~/Downloads" -c "unzip {{TARGET}}" -t "*.zip"
  massrun --tests
""",
    )
    parser.add_argument(
        "-c",
        "--command",
        help="command template containing at least one supported placeholder",
    )
    parser.add_argument(
        "-t",
        "--targets",
        nargs="+",
        metavar="PATTERN",
        help="one or more quoted glob patterns such as \"*.png\" or \"*.zip\"",
    )
    parser.add_argument(
        "-d",
        "--cwd",
        type=Path,
        help="working directory used for target matching and command execution",
    )
    parser.add_argument("--recursive", action="store_true", help="match target patterns in nested directories")
    parser.add_argument("--dry-run", action="store_true", help="print commands without executing them")
    parser.add_argument("--shell", action="store_true", help="run substituted commands through the platform shell")
    parser.add_argument("--fail-fast", action="store_true", help="stop after the first failed command invocation")
    parser.add_argument("--quiet", action="store_true", help="suppress per-target result lines")
    parser.add_argument(
        "--verbose",
        "-v",
        action="count",
        default=0,
        help="print command displays and captured subprocess output; can be stacked",
    )
    parser.add_argument(
        "--self-test",
        "--tests",
        action="store_true",
        help="run built-in self-tests and exit without requiring command or targets",
    )
    return parser


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


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
    """Run focused dependency-free self-tests."""

    tests = [
        _test_argument_validation_and_placeholders,
        _test_target_matching,
        _test_default_execution_and_dry_run,
        _test_shell_fail_fast_and_exit_status,
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


def _test_argument_validation_and_placeholders() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        target = base / "file one.png"
        _write(target, "data")

        code, _, stderr = _capture_main(["-t", "*.png"])
        _assert(code == 2, "missing command should be argparse usage error")
        _assert("--command" in stderr or "-c" in stderr, "missing command should mention command")

        code, _, stderr = _capture_main(["-c", "tool {{TARGET}}"])
        _assert(code == 2, "missing targets should be argparse usage error")
        _assert("--targets" in stderr or "-t" in stderr, "missing targets should mention targets")

        code, _, stderr = _capture_main(["-d", str(base), "-c", "tool", "-t", "*.png"])
        _assert(code == 1, "command without placeholder should fail")
        _assert("placeholder" in stderr, "placeholder error should be reported")

        command = substitute_placeholders("{{TARGET}} {{STEM}} {{NAME}} {{EXT}} {{DIR}}", target, base)
        _assert(command == "file one.png file one file one.png .png .", "placeholder substitution mismatch")


def _test_target_matching() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        _write(base / "b.zip", "zip")
        _write(base / "a.png", "png")
        _write(base / "a-copy.png", "png")
        _write(base / "nested" / "c.png", "png")
        _write(base / "note.txt", "txt")

        targets = find_targets(base, ["*.png", "*.zip", "*.png"])
        _assert([path.name for path in targets] == ["a-copy.png", "a.png", "b.zip"], "targets should dedupe and sort")

        recursive = find_targets(base, ["*.png"], recursive=True)
        _assert([str(path.relative_to(base)) for path in recursive] == ["a-copy.png", "a.png", str(Path("nested") / "c.png")], "recursive targets mismatch")

        code, _, stderr = _capture_main(["-d", str(base), "-c", "tool {{TARGET}}", "-t", "*.missing"])
        _assert(code == 1, "no-match should fail")
        _assert("no targets matched" in stderr, "no-match error should be reported")


def _test_default_execution_and_dry_run() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        target = base / "file one.txt"
        output = base / "args.txt"
        _write(target, "data")

        command = f"{shlex.quote(sys.executable)} -c \"import sys,pathlib; pathlib.Path(sys.argv[2]).write_text(sys.argv[1])\" {{{{TARGET}}}} args.txt"
        code, stdout, stderr = _capture_main(["-d", str(base), "-c", command, "-t", "*.txt"])
        _assert(code == 0, f"default execution should succeed: {stderr}")
        _assert("[+] file one.txt" in stdout, "success result should be printed")
        _assert(output.read_text(encoding="utf-8") == "file one.txt", "target with spaces should remain one argv value")

        dry_output = base / "dry.txt"
        command = f"{shlex.quote(sys.executable)} -c \"import pathlib; pathlib.Path('dry.txt').write_text('bad')\" {{{{TARGET}}}}"
        code, stdout, _ = _capture_main(["-d", str(base), "--dry-run", "-c", command, "-t", "*.txt"])
        _assert(code == 0, "dry-run should succeed")
        _assert("dry-run:" in stdout, "dry-run should print planned command")
        _assert(not dry_output.exists(), "dry-run should not execute command")


def _test_shell_fail_fast_and_exit_status() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        _write(base / "a.txt", "a")
        _write(base / "b.txt", "b")

        shell_command = f"{shlex.quote(sys.executable)} -c \"import pathlib; pathlib.Path('shell-ok.txt').write_text('ok')\" {{{{TARGET}}}}"
        code, _, _ = _capture_main(["-d", str(base), "--shell", "-c", shell_command, "-t", "a.txt"])
        _assert(code == 0, "shell mode should succeed")
        _assert((base / "shell-ok.txt").exists(), "shell mode should execute through cwd")

        fail_command = f"{shlex.quote(sys.executable)} -c \"import sys; sys.exit(1)\" {{{{TARGET}}}}"
        code, stdout, _ = _capture_main(["-d", str(base), "--fail-fast", "-c", fail_command, "-t", "*.txt"])
        _assert(code == 1, "failed command should make batch fail")
        _assert(stdout.count("[!]") == 1, "fail-fast should stop after first failure")

        ok_command = f"{shlex.quote(sys.executable)} -c \"import sys; sys.exit(0)\" {{{{TARGET}}}}"
        code, _, _ = _capture_main(["-d", str(base), "--quiet", "-c", ok_command, "-t", "*.txt"])
        _assert(code == 0, "all successful commands should return zero")


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.self_test:
        return 0 if _run_tests() else 1
    if not args.command:
        parser.error("-c/--command is required unless --self-test is used")
    if not args.targets:
        parser.error("-t/--targets is required unless --self-test is used")

    return run_batch(args)


if __name__ == "__main__":
    sys.exit(main())
