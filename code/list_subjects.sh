#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=code/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

usage() {
    cat <<'USAGE'
Usage: code/list_subjects.sh --config PATH [--output PATH] [--force] [--render-only]

List BIDS participants from BIDS_DIR in deterministic order.

Options:
  --config PATH             Shell configuration file to load.
  --output PATH             Write normalized participant IDs to this file.
  --force                   Permit replacing an existing --output file.
  --render-only, --dry-run  Print the BIDS directory that would be scanned without validating it.
  --help                    Show this help.
USAGE
}

config_path=""
output_path=""
force=0
render_only=0

while (($#)); do
    case "$1" in
        --config) config_path="${2:-}"; shift 2 ;;
        --output) output_path="${2:-}"; shift 2 ;;
        --force) force=1; shift ;;
        --render-only|--dry-run) render_only=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *) die "Unknown argument: $1" ;;
    esac
done

load_config "$config_path"
require_common_config

if is_truthy "$render_only"; then
    info "Render-only: would scan BIDS participant directories matching: ${BIDS_DIR}/sub-*"
    exit 0
fi

participants="$(list_bids_subjects)"
if [[ -z "$participants" ]]; then
    die "No BIDS participants found in: $BIDS_DIR"
fi

if [[ -n "$output_path" ]]; then
    if [[ -e "$output_path" ]] && ! is_truthy "$force"; then
        die "Output file already exists: $output_path. Use --force to replace it."
    fi
    ensure_dir "$(dirname "$output_path")"
    printf '%s\n' "$participants" > "$output_path"
    info "Wrote participant list: $output_path"
else
    printf '%s\n' "$participants"
fi

