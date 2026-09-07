#!/usr/bin/env bash
# CODEPILLS-META-BEGIN
# schema: codepills.tool/v1
# name: mip
# version: 1.0.0
# author: octanima-labs
# description: Print public, private, wired LAN, and wireless LAN IP information.
# repo: https://github.com/octanima-labs/codepills/blob/main/bash/mip.sh
# license: MIT
# usage: bash/mip.sh {public|private|lan|wlan} [OPTIONS]
# tags:
#   - bash
#   - network
#   - ip
# requires:
#   - bash
#   - ip
#   - curl
#   - jq (optional for public --all)
#   - nmcli, iw, or iwgetid (optional for extended interface details)
#   - wl-copy, xclip, xsel, or pbcopy (optional for --copy)
# platforms:
#   - Linux
# CODEPILLS-META-END

SCRIPT_NAME="$(basename -- "$0")"

COLOR_CYAN='\033[36m'
COLOR_GREEN='\033[32m'
COLOR_YELLOW='\033[33m'
COLOR_RED='\033[31m'
COLOR_RESET='\033[0m'

color_enabled() {
  [[ -t 2 && -z ${NO_COLOR:-} && ${TERM:-} != "dumb" ]]
}

status() {
  local kind=$1
  local message=$2
  local prefix
  local color

  shift 2

  case "${kind}" in
    info)
      prefix='[*]'
      color=${COLOR_CYAN}
      ;;
    success)
      prefix='[+]'
      color=${COLOR_GREEN}
      ;;
    warning)
      prefix='[-]'
      color=${COLOR_YELLOW}
      ;;
    error)
      prefix='[!]'
      color=${COLOR_RED}
      ;;
    *)
      prefix='[*]'
      color=${COLOR_CYAN}
      ;;
  esac

  if color_enabled; then
    printf '%b%s%b ' "${color}" "${prefix}" "${COLOR_RESET}" >&2
  else
    printf '%s ' "${prefix}" >&2
  fi

  printf "${message}\n" "$@" >&2
}

print_help() {
  cat <<EOF
Usage:
  mip {public|private|lan|wlan} [OPTIONS]
  ${SCRIPT_NAME} {public|private|lan|wlan} [OPTIONS]
  ${SCRIPT_NAME} -h|--help

Print public, private, wired LAN, and wireless LAN IP information.

Subcommands:
  public    Print the public internet-facing IP address.
  private   Print the default-route private IPv4 address.
  lan       Print the wired Ethernet IPv4 address.
  wlan      Print the wireless LAN IPv4 address.

Common options:
  -a, --all    Print extended details for the selected subcommand.
  -c, --copy   Copy the primary raw IP address when clipboard tooling exists.
  -h, --help   Show help.

Examples:
  mip public
  mip private --all
  mip wlan --copy
EOF
}

print_subcommand_help() {
  local subcommand=$1

  case "${subcommand}" in
    public)
      cat <<EOF
Usage:
  ${SCRIPT_NAME} public [OPTIONS]

Print the public internet-facing IP address.

Options:
  -a, --all    Print available city, country, provider, and DNS details.
  -c, --copy   Copy the raw public IP address when clipboard tooling exists.
  -h, --help   Show this help.
EOF
      ;;
    private)
      cat <<EOF
Usage:
  ${SCRIPT_NAME} private [OPTIONS]

Print the default-route private IPv4 address.

Options:
  -a, --all    Print available interface, gateway, and DNS details.
  -c, --copy   Copy the raw private IP address when clipboard tooling exists.
  -h, --help   Show this help.
EOF
      ;;
    lan)
      cat <<EOF
Usage:
  ${SCRIPT_NAME} lan [OPTIONS]

Print the wired Ethernet IPv4 address.

Options:
  -a, --all    Print available interface and gateway details.
  -c, --copy   Copy the raw wired LAN IP address when clipboard tooling exists.
  -h, --help   Show this help.
EOF
      ;;
    wlan)
      cat <<EOF
Usage:
  ${SCRIPT_NAME} wlan [OPTIONS]

Print the wireless LAN IPv4 address.

Options:
  -a, --all    Print available interface, SSID, and gateway details.
  -c, --copy   Copy the raw wireless LAN IP address when clipboard tooling exists.
  -h, --help   Show this help.
EOF
      ;;
  esac
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    status error 'Required command not found: %s' "$1"
    return 1
  fi
}

parse_common_options() {
  ALL_FLAG=0
  COPY_FLAG=0

  while [[ $# -gt 0 ]]; do
    case "$1" in
      -a|--all)
        ALL_FLAG=1
        ;;
      -c|--copy)
        COPY_FLAG=1
        ;;
      -h|--help)
        HELP_FLAG=1
        ;;
      *)
        status error 'Unknown option for %s: %s' "${CURRENT_SUBCOMMAND}" "$1"
        return 2
        ;;
    esac
    shift
  done
}

copy_to_clipboard() {
  local value=$1

  if command -v wl-copy >/dev/null 2>&1; then
    printf '%s' "${value}" | wl-copy
  elif command -v xclip >/dev/null 2>&1; then
    printf '%s' "${value}" | xclip -selection clipboard
  elif command -v xsel >/dev/null 2>&1; then
    printf '%s' "${value}" | xsel --clipboard --input
  elif command -v pbcopy >/dev/null 2>&1; then
    printf '%s' "${value}" | pbcopy
  else
    return 1
  fi
}

maybe_copy_ip() {
  local ip=$1

  if [[ ${COPY_FLAG} -ne 1 ]]; then
    return 0
  fi

  if copy_to_clipboard "${ip}"; then
    status success 'Copied IP to clipboard.'
  else
    status warning 'Clipboard copy requested, but no supported clipboard command was found.'
  fi

  return 0
}

print_default_ip() {
  printf '%s\n' "$1"
}

dns_servers() {
  local dns=""

  if [[ -f /etc/resolv.conf ]]; then
    dns=$(awk '
      /^nameserver[[:space:]]+/ && $2 !~ /^127\./ && $2 != "::1" {
        if (dns != "") dns = dns ", "
        dns = dns $2
      }
      END { print dns }
    ' /etc/resolv.conf)
  fi

  if [[ -z ${dns} ]] && command -v nmcli >/dev/null 2>&1; then
    dns=$(nmcli dev show 2>/dev/null | awk '
      /IP4\.DNS/ {
        if (dns != "") dns = dns ", "
        dns = dns $2
      }
      END { print dns }
    ')
  fi

  printf '%s\n' "${dns:-Unknown}"
}

default_route_info() {
  local target=${1:-1.1.1.1}

  ip route get "${target}" 2>/dev/null | awk '
    {
      for (i = 1; i <= NF; i++) {
        if ($i == "dev") iface = $(i + 1)
        if ($i == "src") src = $(i + 1)
      }
    }
    END {
      if (src != "") {
        print src " " iface
      }
    }
  '
}

default_gateway_for_interface() {
  local iface=${1:-}

  if [[ -n ${iface} ]]; then
    ip route show default dev "${iface}" 2>/dev/null | awk '$1 == "default" { print $3; exit }'
  else
    ip route show default 2>/dev/null | awk '$1 == "default" { print $3; exit }'
  fi
}

ipv4_for_interface() {
  local iface=$1

  ip -4 -o addr show dev "${iface}" scope global 2>/dev/null | awk '{ sub(/\/.*/, "", $4); print $4; exit }'
}

public_ip_lookup() {
  local ip=""

  ip=$(curl -fsS --connect-timeout 3 --max-time 8 https://ipinfo.io/ip 2>/dev/null) || true
  if [[ -z ${ip} ]]; then
    ip=$(curl -fsS --connect-timeout 3 --max-time 8 https://ifconfig.me/ip 2>/dev/null) || true
  fi

  printf '%s\n' "${ip}"
}

public_ip_json() {
  curl -fsS --connect-timeout 3 --max-time 8 https://ipinfo.io 2>/dev/null
}

private_ip_info() {
  default_route_info 1.1.1.1
}

wired_interfaces() {
  local iface

  for path in /sys/class/net/*; do
    [[ -e ${path} ]] || continue
    iface=$(basename -- "${path}")

    [[ ${iface} == lo ]] && continue
    [[ -d ${path}/wireless ]] && continue

    if [[ -r ${path}/type ]] && [[ $(<"${path}/type") == "1" ]]; then
      printf '%s\n' "${iface}"
    fi
  done
}

wireless_interfaces() {
  local iface

  if command -v iw >/dev/null 2>&1; then
    iw dev 2>/dev/null | awk '$1 == "Interface" { print $2 }'
    return 0
  fi

  for path in /sys/class/net/*; do
    [[ -e ${path} ]] || continue
    iface=$(basename -- "${path}")
    if [[ -d ${path}/wireless ]]; then
      printf '%s\n' "${iface}"
    fi
  done
}

interface_with_ipv4() {
  local iface
  local ip_addr

  while IFS= read -r iface; do
    [[ -n ${iface} ]] || continue
    ip_addr=$(ipv4_for_interface "${iface}")
    if [[ -n ${ip_addr} ]]; then
      printf '%s %s\n' "${ip_addr}" "${iface}"
      return 0
    fi
  done

  return 1
}

wifi_ssid() {
  local iface=$1
  local ssid=""

  if command -v iwgetid >/dev/null 2>&1; then
    ssid=$(iwgetid -r "${iface}" 2>/dev/null) || true
  fi

  if [[ -z ${ssid} ]] && command -v nmcli >/dev/null 2>&1; then
    ssid=$(nmcli -t -f DEVICE,ACTIVE,SSID dev wifi 2>/dev/null | awk -F: -v iface="${iface}" '$1 == iface && $2 == "yes" { print $3; exit }')
  fi

  printf '%s\n' "${ssid:-Unknown}"
}

print_extended_private() {
  local ip_addr=$1
  local iface=$2
  local gateway

  gateway=$(default_gateway_for_interface "${iface}")

  printf 'IP:          %s\n' "${ip_addr}"
  printf 'Interface:   %s\n' "${iface:-Unknown}"
  printf 'Gateway:     %s\n' "${gateway:-Unknown}"
  printf 'DNS Servers: %s\n' "$(dns_servers)"
}

print_extended_lan() {
  local ip_addr=$1
  local iface=$2
  local gateway

  gateway=$(default_gateway_for_interface "${iface}")

  printf 'IP:        %s\n' "${ip_addr}"
  printf 'Interface: %s\n' "${iface:-Unknown}"
  printf 'Gateway:   %s\n' "${gateway:-Unknown}"
}

print_extended_wlan() {
  local ip_addr=$1
  local iface=$2
  local gateway

  gateway=$(default_gateway_for_interface "${iface}")

  printf 'IP:        %s\n' "${ip_addr}"
  printf 'Interface: %s\n' "${iface:-Unknown}"
  printf 'SSID:      %s\n' "$(wifi_ssid "${iface}")"
  printf 'Gateway:   %s\n' "${gateway:-Unknown}"
}

public_ip() {
  local ip_addr
  local json_data
  local city="Unknown"
  local country="Unknown"
  local provider="Unknown"

  CURRENT_SUBCOMMAND=public
  HELP_FLAG=0
  parse_common_options "$@" || return $?

  if [[ ${HELP_FLAG} -eq 1 ]]; then
    print_subcommand_help public
    return 0
  fi

  require_command curl || return 1

  if [[ ${ALL_FLAG} -eq 1 ]]; then
    require_command jq || return 1
    json_data=$(public_ip_json) || {
      status error 'Could not retrieve public IP information.'
      return 1
    }
    ip_addr=$(jq -r '.ip // empty' <<< "${json_data}")
    city=$(jq -r '.city // "Unknown"' <<< "${json_data}")
    country=$(jq -r '.country // "Unknown"' <<< "${json_data}")
    provider=$(jq -r '.org // "Unknown"' <<< "${json_data}")
  else
    ip_addr=$(public_ip_lookup)
  fi

  if [[ -z ${ip_addr} || ${ip_addr} == "null" ]]; then
    status error 'Could not retrieve public IP.'
    return 1
  fi

  if [[ ${ALL_FLAG} -eq 1 ]]; then
    printf 'IP:          %s\n' "${ip_addr}"
    printf 'City:        %s\n' "${city}"
    printf 'Country:     %s\n' "${country}"
    printf 'Provider:    %s\n' "${provider}"
    printf 'DNS Servers: %s\n' "$(dns_servers)"
  else
    print_default_ip "${ip_addr}"
  fi

  maybe_copy_ip "${ip_addr}"
}

private_ip() {
  local route_info
  local ip_addr
  local iface

  CURRENT_SUBCOMMAND=private
  HELP_FLAG=0
  parse_common_options "$@" || return $?

  if [[ ${HELP_FLAG} -eq 1 ]]; then
    print_subcommand_help private
    return 0
  fi

  require_command ip || return 1

  route_info=$(private_ip_info)
  read -r ip_addr iface <<< "${route_info}"

  if [[ -z ${ip_addr} ]]; then
    status error 'Could not retrieve private IP. Are you connected?'
    return 1
  fi

  if [[ ${ALL_FLAG} -eq 1 ]]; then
    print_extended_private "${ip_addr}" "${iface}"
  else
    print_default_ip "${ip_addr}"
  fi

  maybe_copy_ip "${ip_addr}"
}

lan_ip() {
  local iface_info
  local ip_addr
  local iface

  CURRENT_SUBCOMMAND=lan
  HELP_FLAG=0
  parse_common_options "$@" || return $?

  if [[ ${HELP_FLAG} -eq 1 ]]; then
    print_subcommand_help lan
    return 0
  fi

  require_command ip || return 1

  iface_info=$(wired_interfaces | interface_with_ipv4)
  read -r ip_addr iface <<< "${iface_info}"

  if [[ -z ${ip_addr} ]]; then
    status error 'No wired LAN connection with an IPv4 address is available.'
    return 1
  fi

  if [[ ${ALL_FLAG} -eq 1 ]]; then
    print_extended_lan "${ip_addr}" "${iface}"
  else
    print_default_ip "${ip_addr}"
  fi

  maybe_copy_ip "${ip_addr}"
}

wlan_ip() {
  local iface_info
  local ip_addr
  local iface

  CURRENT_SUBCOMMAND=wlan
  HELP_FLAG=0
  parse_common_options "$@" || return $?

  if [[ ${HELP_FLAG} -eq 1 ]]; then
    print_subcommand_help wlan
    return 0
  fi

  require_command ip || return 1

  iface_info=$(wireless_interfaces | interface_with_ipv4)
  read -r ip_addr iface <<< "${iface_info}"

  if [[ -z ${ip_addr} ]]; then
    status error 'No wireless LAN connection with an IPv4 address is available.'
    return 1
  fi

  if [[ ${ALL_FLAG} -eq 1 ]]; then
    print_extended_wlan "${ip_addr}" "${iface}"
  else
    print_default_ip "${ip_addr}"
  fi

  maybe_copy_ip "${ip_addr}"
}

main() {
  local subcommand=${1:-}

  case "${subcommand}" in
    -h|--help)
      print_help
      return 0
      ;;
    public)
      shift
      public_ip "$@"
      ;;
    private)
      shift
      private_ip "$@"
      ;;
    lan)
      shift
      lan_ip "$@"
      ;;
    wlan)
      shift
      wlan_ip "$@"
      ;;
    "")
      status error 'Missing subcommand.'
      print_help >&2
      return 2
      ;;
    *)
      status error 'Unknown subcommand: %s' "${subcommand}"
      print_help >&2
      return 2
      ;;
  esac
}

if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
  main "$@"
fi
