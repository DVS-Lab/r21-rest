#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=code/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

usage() {
    cat <<'USAGE'
Usage: code/run_mriqc_subject.sh [--config PATH] --participant LABEL [options]

Run or render one MRIQC participant command.

Options:
  --config PATH             Optional shell configuration file. Defaults to config/linux.env, then config/linux.env.example.
  --participant LABEL       Participant label, with or without "sub-".
  --dry-run, --render-only  Render the command without validating Linux paths or running the container.
  --force                   Run even if a complete status marker already exists.
  --help                    Show this help.
USAGE
}

config_path=""
participant_input=""
dry_run=0
force=0

while (($#)); do
    case "$1" in
        --config) config_path="${2:-}"; shift 2 ;;
        --participant) participant_input="${2:-}"; shift 2 ;;
        --dry-run|--render-only) dry_run=1; shift ;;
        --force) force=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *) die "Unknown argument: $1" ;;
    esac
done

load_config "$config_path"
require_mriqc_config
[[ -n "$participant_input" ]] || die "--participant LABEL is required."

participant="$(normalize_participant_id "$participant_input")"
participant_arg="$(participant_label_no_prefix "$participant")"
runtime="$(detect_container_runtime "$dry_run")"
work_dir="/scratch"
read -r -a modalities <<< "$MRIQC_MODALITIES"
((${#modalities[@]})) || die "MRIQC_MODALITIES produced no modalities."

cmd=(
    "$runtime" run --cleanenv
    -B "${BIDS_DIR}:/data:ro"
    -B "${MRIQC_OUTPUT_DIR}:/out"
    -B "${WORK_ROOT}:/scratch"
    "$MRIQC_IMAGE"
    /data
    /out
    participant
    --participant-label "$participant_arg"
    --task-id "$TASK_ID"
    --modalities "${modalities[@]}"
    --work-dir "$work_dir"
    --nprocs "$MRIQC_NPROCS"
    --omp-nthreads "$MRIQC_OMP_NTHREADS"
    --mem-gb "$MRIQC_MEM_GB"
)

if is_truthy "${MRIQC_VERBOSE_REPORTS:-0}"; then
    cmd+=(--verbose-reports)
fi
if is_truthy "${MRIQC_NO_SUBMISSION:-0}"; then
    cmd+=(--no-sub)
fi
if is_truthy "${MRIQC_NOTRACK:-0}"; then
    cmd+=(--notrack)
fi

if is_truthy "$dry_run"; then
    info "Dry-run MRIQC command for ${participant}; no Linux paths were validated."
    print_command "${cmd[@]}"
    exit 0
fi

require_linux_execution
validate_dir_exists "BIDS" "$BIDS_DIR"
validate_file_exists "MRIQC image" "$MRIQC_IMAGE"

complete_marker="$(status_marker "mriqc" "$participant" "complete")"
if [[ -f "$complete_marker" ]] && ! is_truthy "$force"; then
    info "Skipping ${participant}; MRIQC complete marker already exists: $complete_marker"
    exit 0
fi

guard_running_marker "mriqc" "$participant"

stamp="$(timestamp_file)"
log_dir="${LOG_ROOT}/mriqc/${participant}"
manifest_dir="${MANIFEST_ROOT}/mriqc/${participant}"
ensure_dir "$MRIQC_OUTPUT_DIR" "$WORK_ROOT" "$log_dir" "$manifest_dir" "$(status_dir "mriqc")"

command_file="${manifest_dir}/${stamp}.command.txt"
stdout_log="${log_dir}/${stamp}.stdout.log"
stderr_log="${log_dir}/${stamp}.stderr.log"
print_command "${cmd[@]}" > "$command_file"
info "Recorded MRIQC command: $command_file"

write_status_marker "mriqc" "$participant" "running" "" "$command_file" "$stdout_log" "$stderr_log"

set +e
"${cmd[@]}" > "$stdout_log" 2> "$stderr_log"
rc=$?
set -e

running_marker="$(status_marker "mriqc" "$participant" "running")"
if [[ -f "$running_marker" ]]; then
    mv "$running_marker" "${running_marker}.${stamp}.finished"
fi

if (( rc == 0 )); then
    write_status_marker "mriqc" "$participant" "complete" "$rc" "$command_file" "$stdout_log" "$stderr_log"
    info "MRIQC completed for ${participant}."
else
    write_status_marker "mriqc" "$participant" "failed" "$rc" "$command_file" "$stdout_log" "$stderr_log"
    warn "MRIQC failed for ${participant}; see $stderr_log"
fi

exit "$rc"
