#!/usr/bin/env bash
set -euo pipefail

# Create and enable a swap file on EndeavourOS / Arch Linux.
#
# Features:
# - Creates a swap file.
# - Enables it immediately.
# - Adds it to /etc/fstab for future boots.
# - Refuses to overwrite an existing file.
# - Avoids duplicate /etc/fstab entries.

DEFAULT_SWAPFILE="/swapfile"
DEFAULT_SWAPSIZE="4G"

SCRIPT_NAME="$(basename -- "$0")"
SWAPFILE="${DEFAULT_SWAPFILE}"
SWAPSIZE="${DEFAULT_SWAPSIZE}"
FSTAB="/etc/fstab"
SWAPFILE_CREATED=0
SWAP_ENABLED=0

print_help() {
  cat <<EOF
Usage:
  sudo ${SCRIPT_NAME} [OPTIONS]

Create, enable, and persist a Linux swap file.

Options:
  -f, --swap-file PATH   Path to the swap file.
                         Default: ${DEFAULT_SWAPFILE}

  -s, --swap-size SIZE   Size of the swap file.
                         Examples: 2G, 4G, 512M
                         Default: ${DEFAULT_SWAPSIZE}

  -h, --help             Show this help message and exit.

Examples:
  sudo ${SCRIPT_NAME}
  sudo ${SCRIPT_NAME} --swap-size 2G
  sudo ${SCRIPT_NAME} --swap-file /var/swapfile --swap-size 4G
EOF
}

cleanup_on_error() {
  local exit_code=$?

  if [[ ${SWAP_ENABLED} -eq 1 ]]; then
    echo "Error: setup failed. Disabling swap file: ${SWAPFILE}" >&2
    swapoff "${SWAPFILE}" || true
  fi

  if [[ ${SWAPFILE_CREATED} -eq 1 && -e "${SWAPFILE}" ]]; then
    echo "Error: setup failed. Removing partially-created swap file: ${SWAPFILE}" >&2
    rm -f -- "${SWAPFILE}" || true
  fi

  exit "${exit_code}"
}

escape_fstab_path() {
  local path=$1

  path=${path//\\/\\134}
  path=${path// /\\040}
  path=${path//$'\t'/\\011}
  printf '%s' "${path}"
}

trap cleanup_on_error ERR

# Parse command-line arguments.
while [[ $# -gt 0 ]]; do
  case "$1" in
    -f|--swap-file)
      if [[ $# -lt 2 || "$2" == -* ]]; then
        echo "Error: $1 requires a PATH argument." >&2
        exit 1
      fi
      SWAPFILE="$2"
      shift 2
      ;;

    -s|--swap-size)
      if [[ $# -lt 2 || "$2" == -* ]]; then
        echo "Error: $1 requires a SIZE argument." >&2
        exit 1
      fi
      SWAPSIZE="$2"
      shift 2
      ;;

    -h|--help)
      print_help
      exit 0
      ;;

    *)
      echo "Error: unknown option: $1" >&2
      echo "Use --help for usage information." >&2
      exit 1
      ;;
  esac
done

# Basic validation.
if [[ -z "${SWAPFILE}" ]]; then
  echo "Error: swap file path cannot be empty." >&2
  exit 1
fi

if [[ -z "${SWAPSIZE}" ]]; then
  echo "Error: swap size cannot be empty." >&2
  exit 1
fi

if [[ "${SWAPFILE}" != /* ]]; then
  echo "Error: swap file path must be absolute: ${SWAPFILE}" >&2
  exit 1
fi

if [[ "${SWAPFILE}" == *$'\n'* ]]; then
  echo "Error: swap file path cannot contain newline characters." >&2
  exit 1
fi

if [[ ! "${SWAPSIZE}" =~ ^[1-9][0-9]*[KMGTP]?$ ]]; then
  echo "Error: invalid swap size: ${SWAPSIZE}" >&2
  echo "Use a positive integer optionally followed by K, M, G, T, or P. Examples: 512M, 2G, 4G" >&2
  exit 1
fi

# Refuse to overwrite an existing file, directory, symlink, or special path.
if [[ -e "${SWAPFILE}" || -L "${SWAPFILE}" ]]; then
  echo "Error: ${SWAPFILE} already exists. Refusing to overwrite it." >&2
  exit 1
fi

# Ensure the parent directory exists.
SWAPDIR="$(dirname -- "${SWAPFILE}")"

if [[ ! -d "${SWAPDIR}" ]]; then
  echo "Error: parent directory does not exist: ${SWAPDIR}" >&2
  exit 1
fi

FSTAB_SWAPFILE="$(escape_fstab_path "${SWAPFILE}")"
SWAP_FSTYPE="$(findmnt --noheadings --output FSTYPE --target "${SWAPDIR}" | tr -d '[:space:]')"

if [[ -z "${SWAP_FSTYPE}" ]]; then
  echo "Error: unable to determine filesystem type for: ${SWAPDIR}" >&2
  exit 1
fi

# Require root privileges before making system changes.
if [[ "${EUID}" -ne 0 ]]; then
  echo "Error: this script must be run as root." >&2
  echo "Run it with: sudo ${SCRIPT_NAME}" >&2
  exit 1
fi

# Create the swap file.
echo "Creating ${SWAPSIZE} swap file at ${SWAPFILE}..."
if [[ "${SWAP_FSTYPE}" == "btrfs" ]]; then
  if ! command -v btrfs >/dev/null 2>&1; then
    echo "Error: btrfs command is required to create swap files on Btrfs filesystems." >&2
    exit 1
  fi

  SWAPFILE_CREATED=1
  btrfs filesystem mkswapfile --size "${SWAPSIZE}" "${SWAPFILE}"
else
  # fallocate is fast and works well on common non-Btrfs Linux filesystems.
  SWAPFILE_CREATED=1
  fallocate -l "${SWAPSIZE}" "${SWAPFILE}"

  # Lock down permissions. Swap files must not be readable by normal users.
  echo "Setting secure permissions..."
  chmod 600 "${SWAPFILE}"

  echo "Formatting swap file..."
  mkswap "${SWAPFILE}"
fi

# Enable swap immediately, without rebooting.
echo "Enabling swap..."
swapon "${SWAPFILE}"
SWAP_ENABLED=1

# Add the swap file to /etc/fstab so it is enabled on future boots.
# Use awk instead of a plain grep substring check, so paths like /swapfile2
# do not accidentally match /swapfile.
if FSTAB_PATH="${FSTAB_SWAPFILE}" awk '
  BEGIN { path = ENVIRON["FSTAB_PATH"] }
  $0 !~ /^[[:space:]]*#/ && $1 == path { found = 1 }
  END { exit found ? 0 : 1 }
' "${FSTAB}"; then
  echo "Notice: ${SWAPFILE} already appears in ${FSTAB}; not adding a duplicate entry."
else
  echo "Adding ${SWAPFILE} to ${FSTAB}..."
  cp "${FSTAB}" "${FSTAB}.bak.$(date +%Y%m%d-%H%M%S)"
  printf '%s none swap defaults 0 0\n' "${FSTAB_SWAPFILE}" >> "${FSTAB}"
fi

SWAPFILE_CREATED=0
SWAP_ENABLED=0

# Show final status.
echo
echo "Swap status:"
swapon --show

echo
echo "Memory summary:"
free -h

echo
echo "Done. Swap file created and configured successfully."
