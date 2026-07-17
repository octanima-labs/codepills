"""Self-contained CLI for pinging multiple targets in parallel.

ping-wave intentionally uses the operating system's ``ping`` executable instead
of HTTP requests, raw sockets, or third-party networking libraries. It chooses
the packet-count option expected by the current platform: ``-n`` on Windows and
``-c`` on Unix-like systems such as Linux and macOS.

The script has no Python package dependencies. The only external requirement is
that a compatible ``ping`` command is available on ``PATH``.
"""

from __future__ import annotations

import argparse
import platform
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path


GREEN = "\033[32m"
RED = "\033[31m"
RESET = "\033[0m"
REQUIRED_TEST_TARGET = "127.0.0.1"
OPTIONAL_TEST_TARGETS = ("1.1.1.1", "8.8.8.8")


@dataclass(frozen=True)
class PingResult:
    """Captured outcome for one target ping attempt."""

    target: str
    reachable: bool
    output: str


def colorize(message: str, color: str) -> str:
    """Wrap a terminal message in a simple ANSI color sequence."""

    return f"{color}{message}{RESET}"


def build_ping_command(target: str, num_packets: int) -> list[str]:
    """Build the platform-specific system ping command for one target."""

    if platform.system().lower() == "windows":
        return ["ping", "-n", str(num_packets), target]
    return ["ping", "-c", str(num_packets), target]


def output_shows_all_packets_lost(output: str) -> bool:
    """Return true when ping output reports that no packets were received.

    Ping output is not standardized across operating systems, so this checks the
    common Linux, macOS, BSD, and Windows phrases that indicate total loss.
    """

    normalized = output.lower()
    return any(
        marker in normalized
        for marker in (
            "100% packet loss",
            "100.0% packet loss",
            "(100% loss)",
            "0 received",
            "0 packets received",
            "received = 0",
        )
    )


def ping_target(target: str, num_packets: int) -> PingResult:
    """Run system ping for one target and capture stdout plus stderr."""

    command = build_ping_command(target, num_packets)

    try:
        completed = subprocess.run(command, capture_output=True, text=True)
    except FileNotFoundError:
        return PingResult(target=target, reachable=False, output="ping command not found\n")

    output = completed.stdout
    if completed.stderr:
        output = f"{output}{completed.stderr}"

    reachable = completed.returncode == 0 and not output_shows_all_packets_lost(output)
    return PingResult(target=target, reachable=reachable, output=output)


def result_line(result: PingResult) -> str:
    """Format the plain-text success or failure line for one target."""

    prefix = "[+]" if result.reachable else "[!]"
    return f"{prefix} {result.target}"


def print_result(result: PingResult, verbosity: int) -> None:
    """Print one target result, optionally followed by raw ping output."""

    line = result_line(result)
    print(colorize(line, GREEN if result.reachable else RED))

    if verbosity:
        print(result.output, end="" if result.output.endswith("\n") else "\n")


def format_file_result(result: PingResult) -> str:
    """Format one file block with summary and full raw ping output."""

    output = result.output if result.output.endswith("\n") else f"{result.output}\n"
    return f"{result_line(result)}\n{output}"


def format_summary(results: list[PingResult]) -> str:
    """Format the aggregate summary for normal target pings."""

    total = len(results)
    reachable = sum(result.reachable for result in results)
    unreachable = total - reachable
    return f"[*] {total} targets tested: reachable {reachable}, unreachable {unreachable}"


def check_targets(targets: list[str], num_packets: int, verbosity: int) -> list[PingResult]:
    """Ping targets concurrently and print each result as it completes."""

    max_workers = min(32, len(targets))
    results: list[PingResult] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(ping_target, target, num_packets) for target in targets]
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print_result(result, verbosity)

    print(format_summary(results))
    return results


def _print_test_result(label: str, result: PingResult, status: str, verbosity: int) -> None:
    """Print one built-in smoke-test result and optional diagnostics."""

    print(f"{label} {result.target}: {status}")
    if verbosity:
        print(result.output, end="" if result.output.endswith("\n") else "\n")


def _run_tests(verbosity: int) -> int:
    """Run built-in smoke tests and return a process exit code.

    The localhost check is required because it verifies that the local system
    can execute ping at all. Public resolver IPs are useful real-world smoke
    targets, but they are optional because internet access may be blocked.
    """

    required_result = ping_target(REQUIRED_TEST_TARGET, num_packets=1)
    optional_results = [ping_target(target, num_packets=1) for target in OPTIONAL_TEST_TARGETS]

    required_status = "PASS" if required_result.reachable else "FAIL"
    _print_test_result("required", required_result, required_status, verbosity)

    optional_passed = 0
    optional_skipped = 0
    for result in optional_results:
        if result.reachable:
            optional_passed += 1
            status = "PASS"
        else:
            optional_skipped += 1
            status = "SKIP (unreachable or blocked)"
        _print_test_result("optional", result, status, verbosity)

    print(
        "summary: "
        f"required={required_status.lower()}, "
        f"optional_passed={optional_passed}, "
        f"optional_skipped={optional_skipped}"
    )
    return 0 if required_result.reachable else 1


def write_output_file(path: Path, results: list[PingResult]) -> None:
    """Write plain-text results plus full raw ping output to a file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    output_blocks = [format_file_result(result) for result in results]
    output_blocks.append(format_summary(results))
    path.write_text("\n".join(output_blocks), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser and detailed help text."""

    parser = argparse.ArgumentParser(
        prog="ping-wave",
        description="Ping one or more targets in parallel using the system ping command.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
behavior:
  ping-wave runs targets in parallel and prints one result line per target,
  followed by a final '[*] Z targets tested: reachable X, unreachable Y' summary.
  Reachable targets are printed as green '[+] IP'. Unreachable targets, targets
  with all packets lost, and missing ping executables are printed as red '[!] IP'.

  By default, stdout only shows the colored result lines. Use -v to also print
  the raw ping output for each target. The -v flag can be stacked for future
  compatibility, but any verbosity level currently enables the raw output.

  When -o/--output is used, the file is plain text with no ANSI colors and
  always includes the full raw ping output for every target plus the final
  summary, regardless of the terminal verbosity level.

tests:
  Use -t/--tests to run built-in smoke tests and exit without requiring target
  arguments. The required test pings 127.0.0.1. The optional tests try 1.1.1.1
  and 8.8.8.8, but unreachable external targets are reported as skips because
  internet access may be unavailable or blocked.

  Test output is a simple summary by default. Add -v to include the raw ping
  output for each test target.

exit codes:
  0  all targets were reachable
  1  one or more targets were unreachable, lost all packets, ping was missing,
     or the required built-in smoke test failed
  2  command-line usage error reported by argparse

examples:
  ping-wave 8.8.8.8
  ping-wave 8.8.8.8 1.1.1.1 -n 2
  ping-wave 8.8.8.8 -v
  ping-wave 8.8.8.8 1.1.1.1 -o results.txt
  ping-wave --tests
  ping-wave --tests -v
""",
    )
    parser.add_argument(
        "targets",
        metavar="IP",
        nargs="*",
        help="IP address or hostname to ping; provide one or more targets unless --tests is used",
    )
    parser.add_argument(
        "-n",
        "--num-packets",
        type=int,
        default=4,
        help="number of packets to send per target; must be at least 1 (default: 4)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="write plain-text result lines and full raw ping output to this file",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="print raw ping output to the terminal; can be stacked",
    )
    parser.add_argument(
        "-t",
        "--tests",
        action="store_true",
        help="run built-in smoke tests and exit; target arguments are not required",
    )
    return parser


def main() -> int:
    """Run the CLI and return the documented process exit code."""

    parser = build_parser()
    args = parser.parse_args()

    if args.num_packets < 1:
        parser.error("--num-packets must be at least 1")

    if args.tests:
        return _run_tests(args.verbose)

    if not args.targets:
        parser.error("the following arguments are required: IP")

    results = check_targets(args.targets, args.num_packets, args.verbose)

    if args.output:
        write_output_file(args.output, results)

    return 1 if any(not result.reachable for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
