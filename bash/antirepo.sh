#!/usr/bin/env bash
# CODEPILLS-META-BEGIN
# schema: codepills.tool/v1
# name: antirepo
# version: 1.0.0
# author: octanima-labs
# description: Compare or sync a downloaded source tree against a clean repository clone.
# repo: https://github.com/octanima-labs/codepills/blob/main/bash/antirepo.sh
# license: MIT
# usage: bash/antirepo.sh {diff|sync} SOURCE DEST [OPTIONS]
# tags:
#   - bash
#   - cli
#   - diff
#   - rsync
#   - repository
# requires:
#   - bash
#   - diff
#   - rsync for sync mode
# platforms:
#   - Linux
#   - macOS
# CODEPILLS-META-END

set -euo pipefail

SCRIPT_NAME="$(basename -- "$0")"

SOURCE=""
DEST=""
SUBCOMMAND=""
DRY_RUN=false
SYNC_MODE=""
EXCLUDE_HIDDEN=false
EXCLUDES=()

print_help() {
  cat <<EOF
Usage:
  ${SCRIPT_NAME} {diff|sync} SOURCE DEST [OPTIONS]
  ${SCRIPT_NAME} --tests
  ${SCRIPT_NAME} -h|--help

Compare or sync a downloaded source tree against a clean repository clone.

Subcommands:
  diff    Show differences between SOURCE and DEST without modifying files.
  sync    Copy included changes from SOURCE into DEST.

Arguments:
  SOURCE  Downloaded source tree or untracked working copy.
  DEST    Clean repository clone to compare or update.

Options:
  -e, --exclude PATTERN  Exclude a path or pattern. Repeatable.
  --exclude-hidden       Exclude hidden files and directories.
  --rebase               Sync without deleting destination-only files. Default.
  --ff                   Mirror SOURCE into DEST, deleting destination-only files.
  --dry-run              Show sync actions without modifying DEST.
  --tests                Run built-in tests.
  -h, --help             Show this help message.

Notes:
  .git/ is always excluded.
  diff reports differences only; sync performs file changes unless --dry-run is used.
  --ff and --rebase are mutually exclusive and only valid with sync.

Examples:
  ${SCRIPT_NAME} diff downloaded-src clean-clone --exclude node_modules
  ${SCRIPT_NAME} sync downloaded-src clean-clone --dry-run
  ${SCRIPT_NAME} sync downloaded-src clean-clone --ff --exclude-hidden
EOF
}

fail() {
  printf 'error: %s\n' "$1" >&2
  return 1
}

status() {
  printf '%s\n' "$1" >&2
}

have_command() {
  command -v "$1" >/dev/null 2>&1
}

require_command() {
  local command_name=$1
  if ! have_command "${command_name}"; then
    fail "required command not found: ${command_name}"
  fi
}

parse_args() {
  if [[ $# -eq 0 ]]; then
    print_help
    return 1
  fi

  case ${1:-} in
    -h|--help)
      print_help
      exit 0
      ;;
    --tests|--self-test)
      run_tests
      exit $?
      ;;
  esac

  if [[ $# -lt 3 ]]; then
    print_help
    return 1
  fi

  SUBCOMMAND=$1
  SOURCE=$2
  DEST=$3
  shift 3

  case ${SUBCOMMAND} in
    diff|sync) ;;
    *)
      print_help
      fail "invalid subcommand: ${SUBCOMMAND}"
      ;;
  esac

  while [[ $# -gt 0 ]]; do
    case $1 in
      -e|--exclude)
        if [[ $# -lt 2 || ${2:-} == -* ]]; then
          fail "--exclude requires a pattern"
        fi
        EXCLUDES+=("$2")
        shift 2
        ;;
      --exclude-hidden)
        EXCLUDE_HIDDEN=true
        shift
        ;;
      --dry-run)
        DRY_RUN=true
        shift
        ;;
      --rebase)
        if [[ -n ${SYNC_MODE} && ${SYNC_MODE} != "rebase" ]]; then
          fail "--ff and --rebase are mutually exclusive"
        fi
        SYNC_MODE="rebase"
        shift
        ;;
      --ff)
        if [[ -n ${SYNC_MODE} && ${SYNC_MODE} != "ff" ]]; then
          fail "--ff and --rebase are mutually exclusive"
        fi
        SYNC_MODE="ff"
        shift
        ;;
      -h|--help)
        print_help
        exit 0
        ;;
      *)
        fail "unknown option: $1"
        ;;
    esac
  done

  if [[ ${SUBCOMMAND} == "diff" ]]; then
    if [[ ${DRY_RUN} == true ]]; then
      fail "--dry-run is only valid with sync"
    fi
    if [[ -n ${SYNC_MODE} ]]; then
      fail "--ff and --rebase are only valid with sync"
    fi
  fi

  if [[ ${SUBCOMMAND} == "sync" && -z ${SYNC_MODE} ]]; then
    SYNC_MODE="rebase"
  fi

  [[ -d ${SOURCE} ]] || fail "SOURCE directory does not exist: ${SOURCE}"
  [[ -d ${DEST} ]] || fail "DEST directory does not exist: ${DEST}"
}

build_diff_args() {
  local args=(-qr -x .git)
  local exclude
  if [[ ${EXCLUDE_HIDDEN} == true ]]; then
    args+=(-x '.*')
  fi
  for exclude in "${EXCLUDES[@]}"; do
    args+=(-x "${exclude}")
  done
  printf '%s\0' "${args[@]}"
}

build_rsync_args() {
  local args=(-av --exclude=.git/)
  local exclude
  if [[ ${DRY_RUN} == true ]]; then
    args+=(--dry-run)
  fi
  if [[ ${SYNC_MODE} == "ff" ]]; then
    args+=(--delete)
  fi
  if [[ ${EXCLUDE_HIDDEN} == true ]]; then
    args+=(--exclude='.*')
  fi
  for exclude in "${EXCLUDES[@]}"; do
    args+=(--exclude="${exclude}")
  done
  printf '%s\0' "${args[@]}"
}

run_diff() {
  require_command diff
  local args=()
  mapfile -d '' -t args < <(build_diff_args)

  status "Running diff between '${SOURCE}' and '${DEST}'"
  set +e
  diff "${args[@]}" "${SOURCE}/" "${DEST}/"
  local diff_status=$?
  set -e

  case ${diff_status} in
    0)
      status "No differences found."
      return 0
      ;;
    1)
      return 1
      ;;
    *)
      return "${diff_status}"
      ;;
  esac
}

run_sync() {
  require_command rsync
  local args=()
  mapfile -d '' -t args < <(build_rsync_args)

  if [[ ${SYNC_MODE} == "ff" ]]; then
    status "Sync mode: ff (delete destination-only files not present in source)"
  else
    status "Sync mode: rebase (preserve destination-only files)"
  fi
  if [[ ${DRY_RUN} == true ]]; then
    status "Dry run: no files will be modified."
  fi

  rsync "${args[@]}" "${SOURCE}/" "${DEST}/"
}

write_file() {
  mkdir -p -- "$(dirname -- "$1")"
  printf '%s\n' "$2" > "$1"
}

assert_test() {
  if [[ $1 != true ]]; then
    printf '[!] %s\n' "$2" >&2
    return 1
  fi
}

test_parse_validation() {
  local tmp
  tmp=$(mktemp -d)
  local source_dir="${tmp}/src"
  local dest_dir="${tmp}/dest"
  mkdir -p -- "${source_dir}" "${dest_dir}"
  bash "${BASH_SOURCE[0]}" sync "${source_dir}" "${dest_dir}" --ff --rebase >/dev/null 2>&1 && return 1
  bash "${BASH_SOURCE[0]}" diff "${source_dir}" "${dest_dir}" --ff >/dev/null 2>&1 && return 1
  rm -rf -- "${tmp}"
}

test_sync_modes() {
  if ! have_command rsync; then
    status "Skipping sync mode tests: rsync not found"
    return 0
  fi

  local tmp
  tmp=$(mktemp -d)
  SOURCE="${tmp}/src"
  DEST="${tmp}/dest"
  mkdir -p -- "${SOURCE}" "${DEST}"
  write_file "${SOURCE}/changed.txt" "source"
  write_file "${DEST}/changed.txt" "dest"
  write_file "${DEST}/extra.txt" "keep"

  SUBCOMMAND="sync"
  DRY_RUN=false
  SYNC_MODE="rebase"
  EXCLUDE_HIDDEN=false
  EXCLUDES=()
  run_sync >/dev/null
  [[ -f ${DEST}/extra.txt ]] || return 1
  [[ $(<"${DEST}/changed.txt") == "source" ]] || return 1

  write_file "${DEST}/extra.txt" "delete"
  SYNC_MODE="ff"
  run_sync >/dev/null
  [[ ! -e ${DEST}/extra.txt ]] || return 1

  rm -rf -- "${tmp}"
}

test_dry_run() {
  if ! have_command rsync; then
    status "Skipping dry-run test: rsync not found"
    return 0
  fi

  local tmp
  tmp=$(mktemp -d)
  SOURCE="${tmp}/src"
  DEST="${tmp}/dest"
  mkdir -p -- "${SOURCE}" "${DEST}"
  write_file "${SOURCE}/new.txt" "new"
  SUBCOMMAND="sync"
  DRY_RUN=true
  SYNC_MODE="ff"
  EXCLUDE_HIDDEN=false
  EXCLUDES=()
  run_sync >/dev/null
  [[ ! -e ${DEST}/new.txt ]] || return 1
  rm -rf -- "${tmp}"
}

test_diff() {
  local tmp
  tmp=$(mktemp -d)
  SOURCE="${tmp}/src"
  DEST="${tmp}/dest"
  mkdir -p -- "${SOURCE}" "${DEST}"
  write_file "${SOURCE}/same.txt" "same"
  write_file "${DEST}/same.txt" "same"
  SUBCOMMAND="diff"
  DRY_RUN=false
  SYNC_MODE=""
  EXCLUDE_HIDDEN=false
  EXCLUDES=()
  run_diff >/dev/null || return 1
  write_file "${DEST}/different.txt" "diff"
  run_diff >/dev/null && return 1
  rm -rf -- "${tmp}"
}

run_tests() {
  local tests=(test_parse_validation test_diff test_sync_modes test_dry_run)
  local failures=0
  local test_name

  for test_name in "${tests[@]}"; do
    if ! "${test_name}"; then
      printf '[!] %s failed\n' "${test_name}" >&2
      failures=$((failures + 1))
    fi
  done

  if [[ ${failures} -gt 0 ]]; then
    printf '%s failed, %s passed\n' "${failures}" "$(( ${#tests[@]} - failures ))"
    return 1
  fi

  printf '%s tests passed\n' "${#tests[@]}"
}

main() {
  parse_args "$@"
  case ${SUBCOMMAND} in
    diff) run_diff ;;
    sync) run_sync ;;
  esac
}

main "$@"
