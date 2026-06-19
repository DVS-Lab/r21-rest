#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=code/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

usage() {
    cat <<'USAGE'
Usage: code/run_mriqc_group.sh [--config PATH] [options]

Run or render MRIQC group-level reporting after participant-level MRIQC.

Options:
  --config PATH             Optional shell configuration file. Defaults to config/linux.env, then config/linux.env.example.
  --dry-run, --render-only  Render the command without validating Linux paths or running the container.
  --force                   Run even if a complete status marker already exists.
  --help                    Show this help.
USAGE
}

config_path=""
dry_run=0
force=0

while (($#)); do
    case "$1" in
        --config) config_path="${2:-}"; shift 2 ;;
        --dry-run|--render-only) dry_run=1; shift ;;
        --force) force=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *) die "Unknown argument: $1" ;;
    esac
done

load_config "$config_path"
require_mriqc_config
runtime="$(detect_container_runtime "$dry_run")"
read -r -a modalities <<< "$MRIQC_MODALITIES"
((${#modalities[@]})) || die "MRIQC_MODALITIES produced no modalities."

cmd=(
    "$runtime" run --cleanenv
    -B "${BIDS_DIR}:${BIDS_DIR}:ro"
    -B "${MRIQC_OUTPUT_DIR}:${MRIQC_OUTPUT_DIR}"
    "$MRIQC_IMAGE"
    "$BIDS_DIR"
    "$MRIQC_OUTPUT_DIR"
    group
    --modalities "${modalities[@]}"
)

if is_truthy "${MRIQC_NO_SUBMISSION:-0}"; then
    cmd+=(--no-sub)
fi
if is_truthy "${MRIQC_NOTRACK:-0}"; then
    cmd+=(--notrack)
fi

if is_truthy "$dry_run"; then
    info "Dry-run MRIQC group command; no Linux paths were validated."
    print_command "${cmd[@]}"
    exit 0
fi

require_linux_execution
validate_dir_exists "BIDS" "$BIDS_DIR"
validate_file_exists "MRIQC image" "$MRIQC_IMAGE"
validate_dir_exists "MRIQC output" "$MRIQC_OUTPUT_DIR"

complete_marker="$(status_marker "mriqc_group" "group" "complete")"
if [[ -f "$complete_marker" ]] && ! is_truthy "$force"; then
    info "Skipping MRIQC group report; complete marker already exists: $complete_marker"
    exit 0
fi

guard_running_marker "mriqc_group" "group"

stamp="$(timestamp_file)"
log_dir="${LOG_ROOT}/mriqc/group"
manifest_dir="${MANIFEST_ROOT}/mriqc/group"
ensure_dir "$log_dir" "$manifest_dir" "$(status_dir "mriqc_group")"

command_file="${manifest_dir}/${stamp}.command.txt"
stdout_log="${log_dir}/${stamp}.stdout.log"
stderr_log="${log_dir}/${stamp}.stderr.log"
print_command "${cmd[@]}" > "$command_file"
info "Recorded MRIQC group command: $command_file"

write_status_marker "mriqc_group" "group" "running" "" "$command_file" "$stdout_log" "$stderr_log"

set +e
"${cmd[@]}" > "$stdout_log" 2> "$stderr_log"
rc=$?
set -e

running_marker="$(status_marker "mriqc_group" "group" "running")"
if [[ -f "$running_marker" ]]; then
    mv "$running_marker" "${running_marker}.${stamp}.finished"
fi

if (( rc == 0 )); then
    write_status_marker "mriqc_group" "group" "complete" "$rc" "$command_file" "$stdout_log" "$stderr_log"
    info "MRIQC group report completed."
else
    write_status_marker "mriqc_group" "group" "failed" "$rc" "$command_file" "$stdout_log" "$stderr_log"
    warn "MRIQC group report failed; see $stderr_log"
fi

exit "$rc"
