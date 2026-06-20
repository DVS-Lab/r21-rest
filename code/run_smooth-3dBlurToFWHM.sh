#!/usr/bin/env bash
set -euo pipefail

# Smooth every run in the ordered MELODIC input list.

usage() {
    cat <<'USAGE'
Usage: code/run_smooth-3dBlurToFWHM.sh [--manifest PATH] [--max-jobs N] [--dry-run]

Smooth and mask the runs in derivatives/fsl/task-rest_run_manifest.tsv.
The output list is ordered within subject as sham, rtpj, vlpfc, both.
USAGE
}

scriptdir="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
maindir="$(dirname "$scriptdir")"
derivdir="${DERIVATIVES_ROOT:-${maindir}/derivatives}"
fsldir="${FSL_OUTPUT_DIR:-${derivdir}/fsl}"
task="${TASK_ID:-rest}"
manifest="${RUN_MANIFEST:-${fsldir}/task-${task}_run_manifest.tsv}"
outputlist="${MELODIC_SMOOTHED_FILELIST:-${fsldir}/melodic_filelist_5mm.txt}"
maxjobs="${SMOOTH_MAX_JOBS:-8}"
dryrun=0

while (($#)); do
    case "$1" in
        --manifest) manifest="${2:-}"; shift 2 ;;
        --max-jobs) maxjobs="${2:-}"; shift 2 ;;
        --dry-run|--render-only) dryrun=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *) echo "ERROR: Unknown argument: $1" >&2; usage >&2; exit 1 ;;
    esac
done

[[ -f "$manifest" ]] || { echo "ERROR: Run manifest not found: $manifest" >&2; exit 1; }
[[ "$maxjobs" =~ ^[1-9][0-9]*$ ]] || {
    echo "ERROR: --max-jobs must be a positive integer." >&2
    exit 1
}

inputs=()
subjects=()
runs=()
conditions=()
outputs=()
while IFS=$'\t' read -r participant acquired_run condition condition_order _events input _confounds; do
    [[ "$participant" == "participant" ]] && continue
    [[ -z "$participant" ]] && continue
    subject="${participant#sub-}"
    order_padded="$(printf '%02d' "$condition_order")"
    inputs+=("$input")
    subjects+=("$subject")
    runs+=("$acquired_run")
    conditions+=("$condition")
    output_prefix="${input%_desc-preproc_bold.nii.gz}"
    outputs+=("${output_prefix}_condition-${condition}_order-${order_padded}_desc-preproc_bold_${SMOOTH_FWHM:-5}mm.nii.gz")
done < "$manifest"

((${#inputs[@]} > 0)) || { echo "ERROR: Run manifest is empty: $manifest" >&2; exit 1; }
printf 'Runs: %d\n' "${#inputs[@]}" >&2
printf 'Target FWHM: %s mm\n' "${SMOOTH_FWHM:-5}" >&2
printf 'Condition order: sham, rtpj, vlpfc, both\n' >&2
printf 'Output list: %s\n' "$outputlist" >&2

logdir="${derivdir}/logs/smoothing"
if ((!dryrun)); then
    mkdir -p "$logdir"
fi

pids=()
failures=0
for index in "${!inputs[@]}"; do
    while [[ "$(jobs -rp | wc -l | tr -d ' ')" -ge "$maxjobs" ]]; do
        sleep 2
    done

    args=(
        "${subjects[$index]}"
        "${runs[$index]}"
        --condition "${conditions[$index]}"
    )
    if ((dryrun)); then
        bash "${scriptdir}/smooth-3dBlurToFWHM.sh" "${args[@]}" --dry-run
        continue
    fi

    logfile="${logdir}/sub-${subjects[$index]}_condition-${conditions[$index]}.log"
    echo "Launching sub-${subjects[$index]} ${conditions[$index]} (acquired run-${runs[$index]}); log: $logfile" >&2
    bash "${scriptdir}/smooth-3dBlurToFWHM.sh" "${args[@]}" >"$logfile" 2>&1 &
    pids+=("$!")
done

if ((dryrun)); then
    exit 0
fi

for pid in "${pids[@]}"; do
    if ! wait "$pid"; then
        failures=1
    fi
done
if ((failures)); then
    echo "ERROR: One or more smoothing jobs failed. Check $logdir" >&2
    exit 1
fi

for output in "${outputs[@]}"; do
    [[ -s "$output" ]] || { echo "ERROR: Missing smoothed output: $output" >&2; exit 1; }
done

mkdir -p "$(dirname "$outputlist")"
printf '%s\n' "${outputs[@]}" >"$outputlist"
echo "All smoothing jobs completed successfully." >&2
echo "Wrote $outputlist" >&2
