#!/usr/bin/env bash
set -euo pipefail

# Regress one run's omnibus confound matrix from its smoothed BOLD data.

usage() {
    cat <<'USAGE'
Usage: code/regress_confounds.sh SUBJECT RUN [--manifest PATH] [--dry-run]

Apply one joint 3dTproject nuisance regression to a smoothed, masked run.
SUBJECT may be 189 or sub-189; RUN may be 01 or run-01.
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

scriptdir="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
maindir="$(dirname "$scriptdir")"
derivdir="${DERIVATIVES_ROOT:-${maindir}/derivatives}"
fsldir="${FSL_OUTPUT_DIR:-${derivdir}/fsl}"
task="${TASK_ID:-rest}"
manifest="${RUN_MANIFEST:-${fsldir}/task-${task}_run_manifest.tsv}"
dryrun=0

while (($#)); do
    case "$1" in
        --manifest) manifest="${2:-}"; shift 2 ;;
        --dry-run|--render-only) dryrun=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *) echo "ERROR: Unknown argument: $1" >&2; usage >&2; exit 1 ;;
    esac
done

sub="${sub#sub-}"
run="${run#run-}"
participant="sub-${sub}"
[[ -f "$manifest" ]] || { echo "ERROR: Run manifest not found: $manifest" >&2; exit 1; }

if ! row="$(
    awk -F '\t' -v participant="$participant" -v run="$run" '
        NR > 1 && $1 == participant && $2 == run { print; matches++ }
        END { if (matches != 1) exit 1 }
    ' "$manifest"
)"; then
    echo "ERROR: Expected one manifest row for $participant run-$run" >&2
    exit 1
fi

IFS=$'\t' read -r _participant _run condition condition_order _events bold confounds <<< "$row"
order_padded="$(printf '%02d' "$condition_order")"
fwhm="${SMOOTH_FWHM:-5}"
smoothed="${bold%_desc-preproc_bold.nii.gz}_condition-${condition}_order-${order_padded}_desc-preproc_bold_${fwhm}mm.nii.gz"
mask="${bold%_desc-preproc_bold.nii.gz}_desc-brain_mask.nii.gz"
outputdir="${DENOISED_OUTPUT_DIR:-${fsldir}/denoised}/${participant}/func"
smoothed_name="$(basename "$smoothed")"
smoothed_suffix="_desc-preproc_bold_${fwhm}mm.nii.gz"
output="${outputdir}/${smoothed_name%$smoothed_suffix}_desc-denoised_bold_${fwhm}mm.nii.gz"

cmd=(
    3dTproject
    -input "$smoothed"
    -mask "$mask"
    -ort "$confounds"
    -polort 0
    -prefix "$output"
)

printf 'Subject: %s\n' "$participant" >&2
printf 'Run: run-%s\n' "$run" >&2
printf 'Condition: %s (order %s)\n' "$condition" "$order_padded" >&2
printf 'Input: %s\n' "$smoothed" >&2
printf 'Confounds: %s\n' "$confounds" >&2
printf 'Mask: %s\n' "$mask" >&2
printf 'Output: %s\n' "$output" >&2
printf 'Command:\n' >&2
printf '%q ' "${cmd[@]}" >&2
printf '\n' >&2

if ((dryrun)); then
    exit 0
fi

for command in 3dTproject fslnvols; do
    command -v "$command" >/dev/null 2>&1 || {
        echo "ERROR: $command is not on PATH." >&2
        exit 1
    }
done
[[ -s "$smoothed" ]] || { echo "ERROR: Smoothed input not found: $smoothed" >&2; exit 1; }
[[ -s "$mask" ]] || { echo "ERROR: Mask not found: $mask" >&2; exit 1; }
[[ -s "$confounds" ]] || { echo "ERROR: Confounds not found: $confounds" >&2; exit 1; }

nvolumes="$(fslnvols "$smoothed")"
if ! confound_shape="$(
    awk '
        NF {
            if (!columns) columns = NF
            if (NF != columns) exit 1
            rows++
        }
        END {
            if (!rows) exit 1
            print rows, columns
        }
    ' "$confounds"
)"; then
    echo "ERROR: Confound matrix is empty or has inconsistent columns: $confounds" >&2
    exit 1
fi
read -r confound_rows confound_columns <<< "$confound_shape"
[[ "$confound_rows" -eq "$nvolumes" ]] || {
    echo "ERROR: $confounds has $confound_rows rows; input has $nvolumes volumes" >&2
    exit 1
}
((confound_columns < nvolumes)) || {
    echo "ERROR: Confound design has $confound_columns columns for $nvolumes volumes" >&2
    exit 1
}
printf 'Design: %d volumes x %d confounds (%d residual dimensions before rank adjustment)\n' \
    "$nvolumes" "$confound_columns" "$((nvolumes - confound_columns - 1))" >&2

if [[ -s "$output" ]]; then
    echo "Output already exists; skipping: $output" >&2
    exit 0
fi

mkdir -p "$outputdir"
OMP_NUM_THREADS="${DENOISE_OMP_THREADS:-4}" "${cmd[@]}"
[[ -s "$output" ]] || { echo "ERROR: 3dTproject did not create: $output" >&2; exit 1; }
[[ "$(fslnvols "$output")" -eq "$nvolumes" ]] || {
    echo "ERROR: Denoised output has the wrong number of volumes: $output" >&2
    exit 1
}
