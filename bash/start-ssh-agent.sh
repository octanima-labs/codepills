#!/usr/bin/env bash
# CODEPILLS-META-BEGIN
# schema: codepills.tool/v1
# name: start-ssh-agent
# version: 1.0.0
# author: octanima-labs
# description: Start or reuse an ssh-agent and load selected SSH keys.
# repo: https://github.com/octanima-labs/codepills/blob/main/bash/start-ssh-agent.sh
# license: MIT
# usage: source bash/start-ssh-agent.sh [PATH ...]
# tags:
#   - bash
#   - ssh
#   - ssh-agent
# requires:
#   - bash
#   - ssh-agent
#   - ssh-add
#   - ssh-keygen
# platforms:
#   - Linux
#   - macOS
# CODEPILLS-META-END

_cp_ssh_agent_script_name="$(basename -- "${BASH_SOURCE[0]}")"

_cp_ssh_agent_print_help() {
  cat <<EOF
Usage:
  source ${_cp_ssh_agent_script_name} [PATH ...]
  ${_cp_ssh_agent_script_name} --help

Start or reuse an ssh-agent and load selected SSH private keys.

Arguments:
  PATH ...    SSH private key paths to load when missing from the agent.

Options:
  -h, --help  Show this help message and return.

.bashrc usage:
  Source this script so SSH_AUTH_SOCK remains available in your shell:

    source /path/to/bash/${_cp_ssh_agent_script_name} ~/.ssh/id_ed25519 ~/.ssh/work

Running the script as a child process can start or reuse an agent, but it cannot
export SSH_AUTH_SOCK back to the parent shell.
EOF
}

_cp_ssh_agent_is_sourced() {
  [[ ${BASH_SOURCE[0]} != "$0" ]]
}

_cp_ssh_agent_have_command() {
  command -v "$1" >/dev/null 2>&1
}

_cp_ssh_agent_color_enabled() {
  [[ -t 2 && -z ${NO_COLOR:-} && ${TERM:-} != "dumb" ]]
}

_cp_ssh_agent_status() {
  local kind=$1
  local format=$2
  local prefix
  local color
  local reset='\033[0m'

  shift 2

  case ${kind} in
    info)
      prefix='[*]'
      color='\033[36m'
      ;;
    success)
      prefix='[+]'
      color='\033[32m'
      ;;
    warning)
      prefix='[-]'
      color='\033[33m'
      ;;
    error)
      prefix='[!]'
      color='\033[31m'
      ;;
    *)
      prefix='[*]'
      color='\033[36m'
      ;;
  esac

  if _cp_ssh_agent_color_enabled; then
    printf '%b%s%b ' "${color}" "${prefix}" "${reset}" >&2
  else
    printf '%s ' "${prefix}" >&2
  fi

  printf "${format}\n" "$@" >&2
}

_cp_ssh_agent_socket_reachable() {
  local socket_path=$1
  local status

  if [[ -z ${socket_path} || ! -S ${socket_path} ]]; then
    return 1
  fi

  SSH_AUTH_SOCK=${socket_path} ssh-add -l >/dev/null 2>&1
  status=$?

  case ${status} in
    0|1) return 0 ;;
    *) return 1 ;;
  esac
}

_cp_ssh_agent_runtime_dir() {
  local fallback_dir

  if [[ -n ${XDG_RUNTIME_DIR:-} && -d ${XDG_RUNTIME_DIR} && -w ${XDG_RUNTIME_DIR} ]]; then
    printf '%s\n' "${XDG_RUNTIME_DIR}"
    return 0
  fi

  fallback_dir="${TMPDIR:-/tmp}"
  fallback_dir="${fallback_dir%/}/codepills-ssh-agent-${UID}"

  if ! mkdir -p -- "${fallback_dir}"; then
    _cp_ssh_agent_status error 'Unable to create ssh-agent runtime directory: %s' "${fallback_dir}"
    return 1
  fi

  chmod 700 -- "${fallback_dir}" 2>/dev/null || true
  printf '%s\n' "${fallback_dir}"
}

_cp_ssh_agent_managed_socket() {
  local runtime_dir

  runtime_dir="$(_cp_ssh_agent_runtime_dir)" || return 1
  printf '%s\n' "${runtime_dir%/}/codepills-ssh-agent.sock"
}

_cp_ssh_agent_start() {
  local socket_path=$1
  local agent_output

  rm -f -- "${socket_path}" 2>/dev/null || true

  _cp_ssh_agent_status info 'Starting ssh-agent...'
  if ! agent_output="$(ssh-agent -a "${socket_path}" -s)"; then
    _cp_ssh_agent_status error 'Failed to start ssh-agent.'
    return 1
  fi

  eval "${agent_output}" >/dev/null
  export SSH_AUTH_SOCK SSH_AGENT_PID
  _cp_ssh_agent_status success 'ssh-agent started.'
}

_cp_ssh_agent_prepare() {
  local managed_socket

  if _cp_ssh_agent_socket_reachable "${SSH_AUTH_SOCK:-}"; then
    export SSH_AUTH_SOCK
    _cp_ssh_agent_status success 'Reusing existing ssh-agent.'
    return 0
  fi

  managed_socket="$(_cp_ssh_agent_managed_socket)" || return 1

  if _cp_ssh_agent_socket_reachable "${managed_socket}"; then
    SSH_AUTH_SOCK=${managed_socket}
    export SSH_AUTH_SOCK
    unset SSH_AGENT_PID
    _cp_ssh_agent_status success 'Reusing managed ssh-agent: %s' "${managed_socket}"
    return 0
  fi

  _cp_ssh_agent_start "${managed_socket}"
}

_cp_ssh_agent_key_fingerprint() {
  local key_path=$1
  local line
  local bits
  local fingerprint
  local comment

  line="$(ssh-keygen -lf "${key_path}" 2>/dev/null)" || return 1
  read -r bits fingerprint comment <<< "${line}"

  if [[ -z ${fingerprint} ]]; then
    return 1
  fi

  printf '%s\n' "${fingerprint}"
}

_cp_ssh_agent_key_loaded() {
  local key_fingerprint=$1
  local line
  local bits
  local loaded_fingerprint
  local comment

  while IFS= read -r line; do
    read -r bits loaded_fingerprint comment <<< "${line}"
    if [[ ${loaded_fingerprint} == "${key_fingerprint}" ]]; then
      return 0
    fi
  done < <(ssh-add -l 2>/dev/null)

  return 1
}

_cp_ssh_agent_load_key() {
  local key_path=$1
  local key_fingerprint

  if [[ ! -f ${key_path} ]]; then
    _cp_ssh_agent_status warning 'SSH key not found: %s' "${key_path}"
    return 1
  fi

  if key_fingerprint="$(_cp_ssh_agent_key_fingerprint "${key_path}")"; then
    if _cp_ssh_agent_key_loaded "${key_fingerprint}"; then
      _cp_ssh_agent_status success 'SSH key already loaded: %s' "${key_path}"
      return 0
    fi
  else
    _cp_ssh_agent_status warning 'Unable to read SSH key fingerprint: %s' "${key_path}"
  fi

  _cp_ssh_agent_status info 'Loading SSH key: %s' "${key_path}"
  if ssh-add "${key_path}"; then
    _cp_ssh_agent_status success 'SSH key loaded: %s' "${key_path}"
    return 0
  fi

  _cp_ssh_agent_status warning 'Failed to load SSH key: %s' "${key_path}"
  return 1
}

_cp_ssh_agent_main() {
  local key_paths=()
  local key_path
  local failed=0

  while [[ $# -gt 0 ]]; do
    case $1 in
      -h|--help)
        _cp_ssh_agent_print_help
        return 0
        ;;
      --)
        shift
        break
        ;;
      -*)
        _cp_ssh_agent_status error 'Unknown option: %s' "$1"
        _cp_ssh_agent_status info 'Use --help for usage information.'
        return 2
        ;;
      *)
        key_paths+=("$1")
        shift
        ;;
    esac
  done

  while [[ $# -gt 0 ]]; do
    key_paths+=("$1")
    shift
  done

  for key_path in ssh-agent ssh-add ssh-keygen; do
    if ! _cp_ssh_agent_have_command "${key_path}"; then
      _cp_ssh_agent_status error 'Required command not found: %s' "${key_path}"
      return 1
    fi
  done

  if ! _cp_ssh_agent_prepare; then
    return 1
  fi

  for key_path in "${key_paths[@]}"; do
    _cp_ssh_agent_load_key "${key_path}" || failed=1
  done

  return "${failed}"
}

_cp_ssh_agent_main "$@"
_cp_ssh_agent_exit=$?

if _cp_ssh_agent_is_sourced; then
  return "${_cp_ssh_agent_exit}"
fi

exit "${_cp_ssh_agent_exit}"
