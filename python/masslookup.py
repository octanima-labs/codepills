# CODEPILLS-META-BEGIN
# schema: codepills.tool/v1
# name: masslookup
# version: 1.0.0
# author: octanima-labs
# description: Resolve multiple DNS targets in parallel and output CSV results.
# repo: https://github.com/octanima-labs/codepills/blob/main/python/masslookup.py
# license: MIT
# usage: python python/masslookup.py [TARGET ...] [OPTIONS]
# tags:
#   - python
#   - cli
#   - dns
#   - csv
# requires:
#   - Python standard library
#   - system nslookup command when --server is used
# platforms:
#   - Linux
#   - macOS
#   - Windows
# CODEPILLS-META-END

"""Resolve many DNS targets concurrently and write CSV results."""

from __future__ import annotations

import argparse
import csv
import io
import ipaddress
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, TextIO


CSV_FIELDS = ["Target", "Resolved_Name", "Resolved_IP", "Status"]
DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$"
)

__all__ = [
    "CSV_FIELDS",
    "LookupResult",
    "MasslookupError",
    "parse_targets",
    "load_targets",
    "parse_nslookup_output",
    "build_nslookup_command",
    "resolve_target_system",
    "resolve_target_nslookup",
    "resolve_target",
    "resolve_targets",
    "write_csv",
]


@dataclass(frozen=True)
class LookupResult:
    """Structured outcome for one DNS lookup target."""

    Target: str
    Resolved_Name: str
    Resolved_IP: str
    Status: str


class MasslookupError(ValueError):
    """Raised when batch lookup input or setup is invalid."""


def is_domain(value: str) -> bool:
    """Return true when value is shaped like a DNS domain name."""

    try:
        ascii_name = value.encode("idna").decode("ascii")
    except UnicodeError:
        return False
    return bool(DOMAIN_RE.fullmatch(ascii_name))


def parse_targets(values: Iterable[str]) -> tuple[list[str], list[str]]:
    """Return valid targets and skipped invalid values."""

    targets: list[str] = []
    skipped: list[str] = []
    for value in values:
        item = str(value).strip()
        if not item:
            continue
        try:
            targets.append(str(ipaddress.ip_address(item)))
        except ValueError:
            if is_domain(item):
                targets.append(item)
            else:
                skipped.append(item)
    return targets, skipped


def load_targets(path: str | os.PathLike[str]) -> list[str]:
    """Load one target per nonblank, non-comment line from path."""

    source = Path(path)
    if not source.is_file():
        raise MasslookupError(f"input file not found: {source}")
    try:
        with source.open("r", encoding="utf-8") as handle:
            return [line.strip() for line in handle if line.strip() and not line.lstrip().startswith("#")]
    except OSError as error:
        raise MasslookupError(f"could not read input file {source}: {error}") from error


def parse_nslookup_output(target: str, raw_stdout: str) -> LookupResult:
    """Parse common nslookup output into a structured lookup result."""

    lines = raw_stdout.splitlines()
    answer_lines = []
    is_answer_section = False
    for line in lines:
        stripped = line.strip()
        if "Non-authoritative answer" in stripped:
            is_answer_section = True
            continue
        if is_answer_section or (
            stripped
            and not stripped.lower().startswith("server:")
            and not stripped.lower().startswith("address:")
        ):
            answer_lines.append(line)

    answer_text = "\n".join(answer_lines)
    names = re.findall(r"(?:Name:\s*|name\s*=\s*)([^\s]+)", answer_text, re.IGNORECASE)
    addresses = re.findall(r"Address:\s*([^\s#]+)", answer_text, re.IGNORECASE)
    resolved_name = names[0].rstrip(".") if names else "N/A"

    if any(char.isalpha() for char in target):
        resolved_ip = addresses[0] if addresses else "N/A"
    else:
        resolved_ip = target

    return LookupResult(target, resolved_name, resolved_ip, "Success")


def build_nslookup_command(target: str, server: str | None = None) -> list[str]:
    """Build an nslookup argv command."""

    command = ["nslookup", target]
    if server:
        command.append(server)
    return command


def resolve_target_system(target: str) -> LookupResult:
    """Resolve one target through the operating system resolver."""

    try:
        ipaddress.ip_address(target)
    except ValueError:
        try:
            infos = socket.getaddrinfo(target, None, type=socket.SOCK_STREAM)
        except OSError as error:
            return LookupResult(target, "N/A", "N/A", f"Failed: {error}")

        addresses = []
        for info in infos:
            address = info[4][0]
            if address not in addresses:
                addresses.append(address)
        return LookupResult(target, target, ";".join(addresses) if addresses else "N/A", "Success")

    try:
        hostname, aliases, _ = socket.gethostbyaddr(target)
    except OSError as error:
        return LookupResult(target, "N/A", target, f"Failed: {error}")

    names = [hostname, *aliases]
    return LookupResult(target, names[0] if names else "N/A", target, "Success")


def resolve_target_nslookup(target: str, server: str) -> LookupResult:
    """Resolve one target using nslookup against a specific server."""

    if shutil.which("nslookup") is None:
        raise MasslookupError("nslookup command not found; omit --server to use system DNS")
    try:
        result = subprocess.run(
            build_nslookup_command(target, server),
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as error:
        return LookupResult(target, "N/A", "N/A", f"Failed (Code {error.returncode})")
    except OSError as error:
        return LookupResult(target, "N/A", "N/A", f"Error: {error}")
    return parse_nslookup_output(target, result.stdout)


def resolve_target(target: str, server: str | None = None) -> LookupResult:
    """Resolve one target with system DNS or server-specific nslookup."""

    if server:
        return resolve_target_nslookup(target, server)
    return resolve_target_system(target)


def resolve_targets(targets: Iterable[str], server: str | None = None, max_workers: int = 10) -> list[LookupResult]:
    """Resolve targets concurrently while preserving input order."""

    target_list = list(targets)
    if not target_list:
        raise MasslookupError("no valid targets found to resolve")
    if max_workers < 1:
        raise MasslookupError("workers must be at least 1")

    results: dict[str, LookupResult] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_target = {
            executor.submit(resolve_target, target, server): target for target in target_list
        }
        for future in as_completed(future_to_target):
            target = future_to_target[future]
            results[target] = future.result()
    return [results[target] for target in target_list if target in results]


def write_csv(results: Iterable[LookupResult], output: TextIO) -> None:
    """Write lookup results as CSV."""

    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for result in results:
        writer.writerow(asdict(result))


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""

    parser = argparse.ArgumentParser(
        prog=Path(__file__).name,
        description="Resolve multiple DNS targets in parallel and output CSV results.",
        epilog="""By default, lookups use the operating system resolver through Python.
Use --server to query a specific DNS server through the system nslookup command.
""",
    )
    parser.add_argument("targets", metavar="TARGET", nargs="*", help="IP address or domain name to resolve")
    parser.add_argument("-s", "--server", help="DNS server to query with nslookup")
    parser.add_argument("-i", "--input", metavar="PATH", type=Path, help="file containing targets, one per line")
    parser.add_argument("-o", "--output", metavar="FILE", type=Path, help="write CSV results to this file")
    parser.add_argument("-w", "--workers", type=int, default=10, help="maximum parallel worker threads (default: 10)")
    parser.add_argument("--tests", "--self-test", dest="tests", action="store_true", help="run built-in dependency-free tests and exit")
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
        _test_parse_targets,
        _test_load_targets,
        _test_parse_nslookup_output,
        _test_write_csv,
        _test_cli_validation,
        _test_resolver_dispatch,
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


def _test_parse_targets() -> None:
    targets, skipped = parse_targets([" 192.0.2.1 ", "2001:db8::1", "example.technology", "bad value", ""])
    _assert(targets == ["192.0.2.1", "2001:db8::1", "example.technology"], "target parsing mismatch")
    _assert(skipped == ["bad value"], "invalid target should be skipped")


def _test_load_targets() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "targets.txt"
        path.write_text("# comment\nexample.com\n\n 192.0.2.2 \n", encoding="utf-8")
        _assert(load_targets(path) == ["example.com", "192.0.2.2"], "loaded targets mismatch")


def _test_parse_nslookup_output() -> None:
    forward = """Server:  resolver\nAddress:  192.0.2.53\n\nNon-authoritative answer:\nName: example.com\nAddress: 93.184.216.34\n"""
    result = parse_nslookup_output("example.com", forward)
    _assert(result.Resolved_Name == "example.com", "forward name mismatch")
    _assert(result.Resolved_IP == "93.184.216.34", "forward address mismatch")

    reverse = """Server: resolver\nAddress: 192.0.2.53\n\n1.2.0.192.in-addr.arpa name = host.example.com.\n"""
    result = parse_nslookup_output("192.0.2.1", reverse)
    _assert(result.Resolved_Name == "host.example.com", "reverse name mismatch")
    _assert(result.Resolved_IP == "192.0.2.1", "reverse address mismatch")


def _test_write_csv() -> None:
    output = io.StringIO()
    write_csv([LookupResult("example.com", "example.com", "93.184.216.34", "Success")], output)
    _assert(output.getvalue().splitlines()[0] == ",".join(CSV_FIELDS), "CSV header mismatch")
    _assert("example.com,example.com,93.184.216.34,Success" in output.getvalue(), "CSV row mismatch")


def _test_cli_validation() -> None:
    code, _, stderr = _capture_main([])
    _assert(code == 2, "missing targets should be argparse error")
    _assert("Please provide at least one TARGET" in stderr, "missing target error should be clear")

    code, _, stderr = _capture_main(["example.com", "--workers", "0"])
    _assert(code == 2, "invalid workers should be argparse error")
    _assert("--workers must be at least 1" in stderr, "workers error should be clear")


def _test_resolver_dispatch() -> None:
    original_system = globals()["resolve_target_system"]
    original_nslookup = globals()["resolve_target_nslookup"]
    calls: list[str] = []

    def fake_system(target: str) -> LookupResult:
        calls.append(f"system:{target}")
        return LookupResult(target, target, "192.0.2.10", "Success")

    def fake_nslookup(target: str, server: str) -> LookupResult:
        calls.append(f"nslookup:{target}:{server}")
        return LookupResult(target, target, "192.0.2.11", "Success")

    try:
        globals()["resolve_target_system"] = fake_system
        globals()["resolve_target_nslookup"] = fake_nslookup
        _assert(resolve_target("example.com").Resolved_IP == "192.0.2.10", "system resolver not used")
        _assert(resolve_target("example.com", "1.1.1.1").Resolved_IP == "192.0.2.11", "nslookup resolver not used")
        _assert(calls == ["system:example.com", "nslookup:example.com:1.1.1.1"], "dispatch calls mismatch")
    finally:
        globals()["resolve_target_system"] = original_system
        globals()["resolve_target_nslookup"] = original_nslookup


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return a process exit code."""

    parser = build_parser()
    args = parser.parse_args(argv)

    if args.tests:
        return 0 if _run_tests() else 1
    if args.workers < 1:
        parser.error("--workers must be at least 1")

    raw_targets = list(args.targets)
    try:
        if args.input:
            raw_targets.extend(load_targets(args.input))
    except MasslookupError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    if not raw_targets:
        parser.error("Please provide at least one TARGET or use -i/--input")

    targets, skipped = parse_targets(raw_targets)
    for item in skipped:
        print(f"warning: skipping invalid target: {item}", file=sys.stderr)
    if not targets:
        print("error: no valid targets found to resolve", file=sys.stderr)
        return 1

    try:
        results = resolve_targets(targets, server=args.server, max_workers=args.workers)
    except MasslookupError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    try:
        if args.output:
            with args.output.open("w", newline="", encoding="utf-8") as handle:
                write_csv(results, handle)
        else:
            write_csv(results, sys.stdout)
    except OSError as error:
        print(f"error: could not write output: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
