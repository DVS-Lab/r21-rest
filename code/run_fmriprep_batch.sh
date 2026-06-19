#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=code/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

usage() {
    cat <<'USAGE'
Usage: code/run_fmriprep_batch.sh [--config PATH] [options]

Run or render fMRIPrep participant jobs with bounded concurrency.

Options:
  --config PATH             Optional shell configuration file. Defaults to config/linux.env, then config/linux.env.example.
  --subjects PATH           Participant list, one label per line.
  --participant LABEL       Add one participant label. May be repeated.
  --pilot-one               Run/render only the first selected participant.
  --max-jobs N              Concurrent jobs. Default: FMRIPREP_MAX_JOBS. N=5 is an explicit override.
  --allow-oversubscribe     Warn but do not fail if projected resources exceed Linux resources.
  --dry-run, --render-only  Render commands without validating Linux paths or running containers.
  --force                   Pass --force to participant launchers.
  --help                    Show this help.
USAGE
}

config_path=""
subjects_file=""
participant_args=()
pilot_one=0
max_jobs=""
allow_oversubscribe=0
dry_run=0
force=0

while (($#)); do
    case "$1" in
        --config) config_path="${2:-}"; shift 2 ;;
        --subjects) subjects_file="${2:-}"; shift 2 ;;
        --participant) participant_args+=("${2:-}"); shift 2 ;;
        --pilot-one) pilot_one=1; shift ;;
        --max-jobs) max_jobs="${2:-}"; shift 2 ;;
        --allow-oversubscribe) allow_oversubscribe=1; shift ;;
        --dry-run|--render-only) dry_run=1; shift ;;
        --force) force=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *) die "Unknown argument: $1" ;;
    esac
done

load_config "$config_path"
require_fmriprep_config
max_jobs="${max_jobs:-$FMRIPREP_MAX_JOBS}"
check_max_jobs "$max_jobs"

subjects=()
if [[ -n "$subjects_file" ]]; then
    while IFS= read -r subject; do
        subjects+=("$subject")
    done < <(read_subjects_file "$subjects_file")
elif ((${#participant_args[@]})); then
    while IFS= read -r subject; do
        subjects+=("$subject")
    done < <(
        for participant in "${participant_args[@]}"; do
            normalize_participant_id "$participant"
        done | LC_ALL=C sort -u
    )
elif is_truthy "$dry_run"; then
    die "Dry-run batch rendering needs --subjects or at least one --participant because BIDS_DIR is not scanned."
else
    while IFS= read -r subject; do
        subjects+=("$subject")
    done < <(list_bids_subjects)
fi

((${#subjects[@]})) || die "No participants selected for fMRIPrep."

if is_truthy "$pilot_one"; then
    subjects=("${subjects[0]}")
    info "Pilot mode selected one participant: ${subjects[0]}"
fi

active_jobs="$max_jobs"
if (( ${#subjects[@]} < active_jobs )); then
    active_jobs="${#subjects[@]}"
fi
check_batch_resources "fMRIPrep" "$active_jobs" "$FMRIPREP_NPROCS" "$FMRIPREP_MEM_MB" "$allow_oversubscribe" "$dry_run"

subject_flags=(--config "$config_path")
if is_truthy "$dry_run"; then
    subject_flags+=(--dry-run)
fi
if is_truthy "$force"; then
    subject_flags+=(--force)
fi

if is_truthy "$dry_run"; then
    info "Rendering fMRIPrep commands for ${#subjects[@]} participant(s)."
    for subject in "${subjects[@]}"; do
        "${SCRIPT_DIR}/run_fmriprep_subject.sh" "${subject_flags[@]}" --participant "$subject"
    done
    exit 0
fi

require_linux_execution
stamp="$(timestamp_file)"
batch_manifest_dir="${MANIFEST_ROOT}/fmriprep"
ensure_dir "$batch_manifest_dir" "${LOG_ROOT}/fmriprep"
batch_manifest="${batch_manifest_dir}/${stamp}.batch.tsv"
{
    printf 'participant\tcommand\n'
    for subject in "${subjects[@]}"; do
        printf '%s\t' "$subject"
        print_command "${SCRIPT_DIR}/run_fmriprep_subject.sh" "${subject_flags[@]}" --participant "$subject"
    done
} > "$batch_manifest"
info "Recorded fMRIPrep batch manifest: $batch_manifest"

failures=0
running=0
for subject in "${subjects[@]}"; do
    while (( running >= max_jobs )); do
        if ! wait -n; then
            failures=1
        fi
        running="$(( running - 1 ))"
    done
    "${SCRIPT_DIR}/run_fmriprep_subject.sh" "${subject_flags[@]}" --participant "$subject" &
    running="$(( running + 1 ))"
done

while (( running > 0 )); do
    if ! wait -n; then
        failures=1
    fi
    running="$(( running - 1 ))"
done

if (( failures )); then
    die "One or more fMRIPrep participant jobs failed."
fi
info "All selected fMRIPrep participant jobs finished successfully."
