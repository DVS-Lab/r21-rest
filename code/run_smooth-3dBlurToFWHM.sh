#!/usr/bin/env bash
set -euo pipefail

# Smooth every run in the ordered MELODIC input list.

usage() {
    cat <<'USAGE'
Usage: code/run_smooth-3dBlurToFWHM.sh [--input-list PATH] [--max-jobs N] [--dry-run]

Smooth each run in derivatives/fsl/melodic_filelist.txt to 5-mm FWHM and
write the parallel ordered list derivatives/fsl/melodic_filelist_5mm.txt.
USAGE
}

scriptdir="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
maindir="$(dirname "$scriptdir")"
derivdir="${DERIVATIVES_ROOT:-${maindir}/derivatives}"
fsldir="${FSL_OUTPUT_DIR:-${derivdir}/fsl}"
inputlist="${MELODIC_UNSMOOTHED_FILELIST:-${fsldir}/melodic_filelist.txt}"
outputlist="${MELODIC_SMOOTHED_FILELIST:-${fsldir}/melodic_filelist_5mm.txt}"
maxjobs="${SMOOTH_MAX_JOBS:-8}"
dryrun=0

while (($#)); do
    case "$1" in
        --input-list) inputlist="${2:-}"; shift 2 ;;
        --max-jobs) maxjobs="${2:-}"; shift 2 ;;
        --dry-run|--render-only) dryrun=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *) echo "ERROR: Unknown argument: $1" >&2; usage >&2; exit 1 ;;
    esac
done

[[ -f "$inputlist" ]] || { echo "ERROR: Input list not found: $inputlist" >&2; exit 1; }
[[ "$maxjobs" =~ ^[1-9][0-9]*$ ]] || {
    echo "ERROR: --max-jobs must be a positive integer." >&2
    exit 1
}

inputs=()
subjects=()
runs=()
outputs=()
while IFS= read -r input || [[ -n "$input" ]]; do
    [[ -z "$input" ]] && continue
    name="$(basename "$input")"
    if [[ "$name" =~ ^sub-([^_]+)_.*_run-([^_]+)_.*_desc-preproc_bold\.nii\.gz$ ]]; then
        subject="${BASH_REMATCH[1]}"
        run="${BASH_REMATCH[2]}"
    else
        echo "ERROR: Cannot determine subject and run from: $input" >&2
        exit 1
    fi
    inputs+=("$input")
    subjects+=("$subject")
    runs+=("$run")
    outputs+=("${input%.nii.gz}_${SMOOTH_FWHM:-5}mm.nii.gz")
done < "$inputlist"

((${#inputs[@]} > 0)) || { echo "ERROR: Input list is empty: $inputlist" >&2; exit 1; }
printf 'Runs: %d\n' "${#inputs[@]}" >&2
printf 'Target FWHM: %s mm\n' "${SMOOTH_FWHM:-5}" >&2
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

    args=("${subjects[$index]}" "${runs[$index]}")
    if ((dryrun)); then
        bash "${scriptdir}/smooth-3dBlurToFWHM.sh" "${args[@]}" --dry-run
        continue
    fi

    logfile="${logdir}/sub-${subjects[$index]}_run-${runs[$index]}.log"
    echo "Launching sub-${subjects[$index]} run-${runs[$index]}; log: $logfile" >&2
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
