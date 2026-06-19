#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=code/lib/common.sh
source "${SCRIPT_DIR}/lib/common.sh"

usage() {
    cat <<'USAGE'
Usage: code/preflight_linux.sh [--config PATH] [--render-only] [--allow-oversubscribe]

Validate the Linux preprocessing configuration without running fMRIPrep or MRIQC.

Options:
  --config PATH             Optional shell configuration file. Defaults to config/linux.env, then config/linux.env.example.
  --render-only, --dry-run  Load settings and print projected resources without validating Linux paths.
  --allow-oversubscribe     Warn but do not fail when projected resources exceed Linux resources.
  --help                    Show this help.
USAGE
}

config_path=""
render_only=0
allow_oversubscribe=0

while (($#)); do
    case "$1" in
        --config) config_path="${2:-}"; shift 2 ;;
        --render-only|--dry-run) render_only=1; shift ;;
        --allow-oversubscribe) allow_oversubscribe=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *) die "Unknown argument: $1" ;;
    esac
done

load_config "$config_path"
require_fmriprep_config
require_mriqc_config

fmriprep_mem_mb="$FMRIPREP_MEM_MB"
mriqc_mem_mb="$(gb_to_mb "$MRIQC_MEM_GB")"

info "Repository root: $REPO_ROOT"
info "Project: $PROJECT_NAME"
info "Task ID: $TASK_ID"
info "Container runtime setting: $CONTAINER_RUNTIME"
runtime="$(detect_container_runtime "$render_only")"
info "Resolved container runtime: $runtime"

check_max_jobs "$FMRIPREP_MAX_JOBS"
check_max_jobs "$MRIQC_MAX_JOBS"
check_batch_resources "fMRIPrep" "$FMRIPREP_MAX_JOBS" "$FMRIPREP_NPROCS" "$fmriprep_mem_mb" "$allow_oversubscribe" "$render_only"
check_batch_resources "MRIQC" "$MRIQC_MAX_JOBS" "$MRIQC_NPROCS" "$mriqc_mem_mb" "$allow_oversubscribe" "$render_only"

if ! is_truthy "$render_only"; then
    require_linux_execution
    validate_dir_exists "BIDS" "$BIDS_DIR"
    validate_file_exists "fMRIPrep image" "$FMRIPREP_IMAGE"
    validate_file_exists "MRIQC image" "$MRIQC_IMAGE"
    validate_dir_exists "TemplateFlow" "$TEMPLATEFLOW_DIR"
    validate_file_exists "FreeSurfer license" "$FS_LICENSE"
    info "Linux paths and runtime validated. No neuroimaging command was run."
else
    info "Render-only preflight complete. Linux-only paths were not validated."
fi
