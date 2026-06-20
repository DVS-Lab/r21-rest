#!/usr/bin/env bash
set -euo pipefail

# Smooth one fMRIPrep task-rest run to a final 5-mm FWHM.

usage() {
    cat <<'USAGE'
Usage: code/smooth-3dBlurToFWHM.sh SUBJECT RUN [--condition LABEL] [--dry-run]

Smooth and mask one native-resolution MNI152NLin6Asym BOLD run to 5-mm FWHM.
The condition is read from the BIDS events file unless supplied by the batch
launcher. SUBJECT may be 189 or sub-189; RUN may be 01 or run-01.
USAGE
}

sub="${1:-}"
run="${2:-}"
if [[ -z "$sub" || -z "$run" || "$sub" == "--help" || "$sub" == "-h" ]]; then
    usage
    [[ "$sub" == "--help" || "$sub" == "-h" ]] && exit 0
    exit 1
fi
shift 2

dryrun=0
condition=""
while (($#)); do
    case "$1" in
        --condition) condition="${2:-}"; shift 2 ;;
        --dry-run|--render-only) dryrun=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *) echo "ERROR: Unknown argument: $1" >&2; usage >&2; exit 1 ;;
    esac
done

sub="${sub#sub-}"
run="${run#run-}"
[[ "$sub" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || {
    echo "ERROR: Invalid participant label: $sub" >&2
    exit 1
}
[[ "$run" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || {
    echo "ERROR: Invalid run label: $run" >&2
    exit 1
}

scriptdir="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
maindir="$(dirname "$scriptdir")"
derivdir="${DERIVATIVES_ROOT:-${maindir}/derivatives}"
fmriprepdir="${FMRIPREP_OUTPUT_DIR:-${derivdir}/fmriprep-25.2.5}"
bidsdir="${BIDS_DIR:-/ZPOOL/data/projects/r21-cardgame/bids}"
scratchroot="${WORK_ROOT:-/ZPOOL/data/scratch/${USER:-$(whoami)}}"
task="${TASK_ID:-rest}"
space="${FMRIPREP_VOLUME_SPACE:-MNI152NLin6Asym}"
fwhm="${SMOOTH_FWHM:-5}"
[[ "$fwhm" =~ ^[0-9]+([.][0-9]+)?$ ]] || {
    echo "ERROR: SMOOTH_FWHM must be numeric: $fwhm" >&2
    exit 1
}

funcdir="${fmriprepdir}/sub-${sub}/func"
shopt -s nullglob
inputs=("${funcdir}/sub-${sub}_task-${task}_run-${run}_space-${space}"*_desc-preproc_bold.nii.gz)
shopt -u nullglob
if ((${#inputs[@]} != 1)); then
    echo "ERROR: Expected one input for sub-${sub} run-${run}; found ${#inputs[@]} in $funcdir" >&2
    exit 1
fi

input="${inputs[0]}"
mask="${input%_desc-preproc_bold.nii.gz}_desc-brain_mask.nii.gz"
events="${bidsdir}/sub-${sub}/func/sub-${sub}_task-${task}_run-${run}_events.tsv"

if [[ -z "$condition" ]]; then
    [[ -f "$events" ]] || { echo "ERROR: Events file not found: $events" >&2; exit 1; }
    if ! condition="$({
        awk -F '\t' '
            NR == 1 {
                for (i = 1; i <= NF; i++) if ($i == "trial_type") column = i
                if (!column) exit 2
                next
            }
            column && $column != "" { labels[tolower($column)] = 1 }
            END {
                for (label in labels) { count++; value = label }
                if (count != 1) exit 3
                print value
            }
        ' "$events"
    })"; then
        echo "ERROR: Expected one trial_type in: $events" >&2
        exit 1
    fi
fi
condition="$(printf '%s' "$condition" | tr '[:upper:]' '[:lower:]')"
case "$condition" in
    sham) condition_order="01" ;;
    rtpj) condition_order="02" ;;
    vlpfc) condition_order="03" ;;
    both) condition_order="04" ;;
    *) echo "ERROR: Unknown condition: $condition" >&2; exit 1 ;;
esac

output="${input%_desc-preproc_bold.nii.gz}_condition-${condition}_order-${condition_order}_desc-preproc_bold_${fwhm}mm.nii.gz"
workdir="${SMOOTH_WORK_DIR:-${scratchroot}/r21-rest/smoothing/sub-${sub}/run-${run}}"
smoothed="${workdir}/$(basename "${output%.nii.gz}")_unmasked.nii.gz"

smooth_cmd=(
    3dBlurToFWHM
    -FWHM "$fwhm"
    -input "$input"
    -prefix "$smoothed"
    -mask "$mask"
)
mask_cmd=(fslmaths "$smoothed" -mas "$mask" "$output")

printf 'Subject: sub-%s\n' "$sub" >&2
printf 'Run: run-%s\n' "$run" >&2
printf 'Condition: %s (order %s)\n' "$condition" "$condition_order" >&2
printf 'Input: %s\n' "$input" >&2
printf 'Mask: %s\n' "$mask" >&2
printf 'Output: %s\n' "$output" >&2
printf 'Scratch: %s\n' "$workdir" >&2
printf 'Commands:\n' >&2
printf '%q ' "${smooth_cmd[@]}" >&2
printf '\n' >&2
printf '%q ' "${mask_cmd[@]}" >&2
printf '\n' >&2

if ((dryrun)); then
    exit 0
fi

command -v 3dBlurToFWHM >/dev/null 2>&1 || {
    echo "ERROR: 3dBlurToFWHM is not on PATH." >&2
    exit 1
}
command -v fslmaths >/dev/null 2>&1 || {
    echo "ERROR: fslmaths is not on PATH." >&2
    exit 1
}
[[ -f "$input" ]] || { echo "ERROR: Input not found: $input" >&2; exit 1; }
[[ -f "$mask" ]] || { echo "ERROR: Mask not found: $mask" >&2; exit 1; }
if [[ -s "$output" ]]; then
    echo "Output already exists; skipping: $output" >&2
    exit 0
fi

mkdir -p "$workdir"
rm -f "$smoothed" "${workdir}/3dFWHMx.1D" "${workdir}/3dFWHMx.1D.png"
(
    cd "$workdir"
    OMP_NUM_THREADS="${SMOOTH_OMP_THREADS:-2}" "${smooth_cmd[@]}"
)
"${mask_cmd[@]}"
[[ -s "$output" ]] || { echo "ERROR: Smoothing did not create: $output" >&2; exit 1; }
rm -f "$smoothed"
