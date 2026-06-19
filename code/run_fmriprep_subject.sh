#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=code/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

usage() {
    cat <<'USAGE'
Usage: code/run_fmriprep_subject.sh [--config PATH] --participant LABEL [options]

Run or render one fMRIPrep participant command.

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
require_fmriprep_config
[[ -n "$participant_input" ]] || die "--participant LABEL is required."

participant="$(normalize_participant_id "$participant_input")"
participant_arg="$(participant_label_no_prefix "$participant")"
runtime="$(detect_container_runtime "$dry_run")"
work_dir="${WORK_ROOT}/fmriprep/${participant}"

output_spaces=("MNI152NLin2009cAsym:res-2" "T1w")
case "$FMRIPREP_PROFILE" in
    volumetric)
        ;;
    surface|cifti)
        if [[ -n "${SURFACE_OUTPUT_SPACES:-}" ]]; then
            read -r -a surface_spaces <<< "$SURFACE_OUTPUT_SPACES"
            output_spaces+=("${surface_spaces[@]}")
        fi
        ;;
    *)
        die "FMRIPREP_PROFILE must be volumetric, surface, or cifti; got: $FMRIPREP_PROFILE"
        ;;
esac

cmd=(
    "$runtime" run --cleanenv
    -B "${BIDS_DIR}:${BIDS_DIR}:ro"
    -B "${FMRIPREP_OUTPUT_DIR}:${FMRIPREP_OUTPUT_DIR}"
    -B "${FS_SUBJECTS_DIR}:${FS_SUBJECTS_DIR}"
    -B "${WORK_ROOT}:${WORK_ROOT}"
    -B "${TEMPLATEFLOW_DIR}:${TEMPLATEFLOW_DIR}:ro"
    -B "${FS_LICENSE}:${FS_LICENSE}:ro"
    --env "TEMPLATEFLOW_HOME=${TEMPLATEFLOW_DIR}"
    --env "FS_LICENSE=${FS_LICENSE}"
    "$FMRIPREP_IMAGE"
    "$BIDS_DIR"
    "$FMRIPREP_OUTPUT_DIR"
    participant
    --participant-label "$participant_arg"
    --task-id "$TASK_ID"
    --fs-license-file "$FS_LICENSE"
    --fs-subjects-dir "$FS_SUBJECTS_DIR"
    --work-dir "$work_dir"
    --nprocs "$FMRIPREP_NPROCS"
    --omp-nthreads "$FMRIPREP_OMP_NTHREADS"
    --mem-mb "$FMRIPREP_MEM_MB"
    --output-spaces "${output_spaces[@]}"
)

if [[ "$FMRIPREP_PROFILE" == "cifti" ]]; then
    cmd+=(--cifti-output "$CIFTI_DENSITY")
fi
if is_truthy "${FMRIPREP_SKIP_BIDS_VALIDATION:-0}"; then
    cmd+=(--skip-bids-validation)
fi
if is_truthy "${FMRIPREP_RESOURCE_MONITOR:-0}"; then
    cmd+=(--resource-monitor)
fi
if is_truthy "${FMRIPREP_NOTRACK:-0}"; then
    cmd+=(--notrack)
fi

if is_truthy "$dry_run"; then
    info "Dry-run fMRIPrep command for ${participant}; no Linux paths were validated."
    print_command "${cmd[@]}"
    exit 0
fi

require_linux_execution
validate_dir_exists "BIDS" "$BIDS_DIR"
validate_file_exists "fMRIPrep image" "$FMRIPREP_IMAGE"
validate_dir_exists "TemplateFlow" "$TEMPLATEFLOW_DIR"
validate_file_exists "FreeSurfer license" "$FS_LICENSE"

complete_marker="$(status_marker "fmriprep" "$participant" "complete")"
if [[ -f "$complete_marker" ]] && ! is_truthy "$force"; then
    info "Skipping ${participant}; fMRIPrep complete marker already exists: $complete_marker"
    exit 0
fi

guard_running_marker "fmriprep" "$participant"

stamp="$(timestamp_file)"
log_dir="${LOG_ROOT}/fmriprep/${participant}"
manifest_dir="${MANIFEST_ROOT}/fmriprep/${participant}"
ensure_dir "$FMRIPREP_OUTPUT_DIR" "$FS_SUBJECTS_DIR" "$work_dir" "$log_dir" "$manifest_dir" "$(status_dir "fmriprep")"

command_file="${manifest_dir}/${stamp}.command.txt"
stdout_log="${log_dir}/${stamp}.stdout.log"
stderr_log="${log_dir}/${stamp}.stderr.log"
print_command "${cmd[@]}" > "$command_file"
info "Recorded fMRIPrep command: $command_file"

write_status_marker "fmriprep" "$participant" "running" "" "$command_file" "$stdout_log" "$stderr_log"

set +e
"${cmd[@]}" > "$stdout_log" 2> "$stderr_log"
rc=$?
set -e

running_marker="$(status_marker "fmriprep" "$participant" "running")"
if [[ -f "$running_marker" ]]; then
    mv "$running_marker" "${running_marker}.${stamp}.finished"
fi

if (( rc == 0 )); then
    write_status_marker "fmriprep" "$participant" "complete" "$rc" "$command_file" "$stdout_log" "$stderr_log"
    info "fMRIPrep completed for ${participant}."
else
    write_status_marker "fmriprep" "$participant" "failed" "$rc" "$command_file" "$stdout_log" "$stderr_log"
    warn "fMRIPrep failed for ${participant}; see $stderr_log"
fi

exit "$rc"
