#!/usr/bin/env bash
set -euo pipefail

# Regress confounds from every run in the ordered run manifest.

usage() {
    cat <<'USAGE'
Usage: code/run_regress_confounds.sh [--manifest PATH] [--max-jobs N] [--dry-run]

Apply one joint nuisance regression to each smoothed run and write the ordered
denoised MELODIC input list.
USAGE
}

scriptdir="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
maindir="$(dirname "$scriptdir")"
derivdir="${DERIVATIVES_ROOT:-${maindir}/derivatives}"
fsldir="${FSL_OUTPUT_DIR:-${derivdir}/fsl}"
task="${TASK_ID:-rest}"
manifest="${RUN_MANIFEST:-${fsldir}/task-${task}_run_manifest.tsv}"
outputdir="${DENOISED_OUTPUT_DIR:-${fsldir}/denoised}"
outputlist="${MELODIC_DENOISED_FILELIST:-${fsldir}/melodic_filelist_5mm_denoised.txt}"
maxjobs="${DENOISE_MAX_JOBS:-8}"
fwhm="${SMOOTH_FWHM:-5}"
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

subjects=()
runs=()
conditions=()
confound_files=()
outputs=()
while IFS=$'\t' read -r participant acquired_run condition condition_order _events bold confounds; do
    [[ "$participant" == "participant" ]] && continue
    [[ -z "$participant" ]] && continue
    order_padded="$(printf '%02d' "$condition_order")"
    smoothed_name="$(basename "${bold%_desc-preproc_bold.nii.gz}_condition-${condition}_order-${order_padded}_desc-preproc_bold_${fwhm}mm.nii.gz")"
    smoothed_suffix="_desc-preproc_bold_${fwhm}mm.nii.gz"
    outputs+=("${outputdir}/${participant}/func/${smoothed_name%$smoothed_suffix}_desc-denoised_bold_${fwhm}mm.nii.gz")
    subjects+=("${participant#sub-}")
    runs+=("$acquired_run")
    conditions+=("$condition")
    confound_files+=("$confounds")
done < "$manifest"

((${#subjects[@]} > 0)) || { echo "ERROR: Run manifest is empty: $manifest" >&2; exit 1; }

for confounds in "${confound_files[@]}"; do
    [[ -s "$confounds" ]] || { echo "ERROR: Confounds not found: $confounds" >&2; exit 1; }
    [[ "$confounds" == *.1D ]] || {
        echo "ERROR: Stale .tsv confound path in run manifest: $confounds" >&2
        echo "AFNI treats the first row of every .tsv as a header." >&2
        echo "Re-run: python3 code/MakeConfounds.py" >&2
        exit 1
    }
    if ! confound_columns="$(
        awk '
            NF {
                if (!columns) columns = NF
                if (NF != columns) exit 1
            }
            END {
                if (!columns) exit 1
                print columns
            }
        ' "$confounds"
    )"; then
        echo "ERROR: Confound matrix is empty or has inconsistent columns: $confounds" >&2
        exit 1
    fi
    ((confound_columns >= 31)) || {
        echo "ERROR: Stale confound matrix has $confound_columns columns; expected at least 31: $confounds" >&2
        echo "Re-run: python3 code/MakeConfounds.py" >&2
        exit 1
    }
done

printf 'Runs: %d\n' "${#subjects[@]}" >&2
printf 'Maximum concurrent jobs: %d\n' "$maxjobs" >&2
printf 'Output list: %s\n' "$outputlist" >&2

logdir="${derivdir}/logs/confound_regression"
if ((!dryrun)); then
    mkdir -p "$logdir"
fi

pids=()
failures=0
for index in "${!subjects[@]}"; do
    while [[ "$(jobs -rp | wc -l | tr -d ' ')" -ge "$maxjobs" ]]; do
        sleep 2
    done

    args=("${subjects[$index]}" "${runs[$index]}" --manifest "$manifest")
    if ((dryrun)); then
        bash "${scriptdir}/regress_confounds.sh" "${args[@]}" --dry-run
        continue
    fi

    logfile="${logdir}/sub-${subjects[$index]}_condition-${conditions[$index]}.log"
    echo "Launching sub-${subjects[$index]} ${conditions[$index]}; log: $logfile" >&2
    bash "${scriptdir}/regress_confounds.sh" "${args[@]}" >"$logfile" 2>&1 &
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
    echo "ERROR: One or more confound regressions failed. Check $logdir" >&2
    exit 1
fi

for output in "${outputs[@]}"; do
    [[ -s "$output" ]] || { echo "ERROR: Missing denoised output: $output" >&2; exit 1; }
done

mkdir -p "$(dirname "$outputlist")"
printf '%s\n' "${outputs[@]}" >"$outputlist"
echo "All confound regressions completed successfully." >&2
echo "Wrote $outputlist" >&2
