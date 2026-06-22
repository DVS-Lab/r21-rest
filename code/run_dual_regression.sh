#!/usr/bin/env bash
set -euo pipefail

# Run standard FSL dual regression with one denoised group-ICA solution.

usage() {
    cat <<'USAGE'
Usage: code/run_dual_regression.sh {0|20} [--dry-run]

Run stages 1 and 2 of the original FSL dual_regression script using the
denoised automatic- or fixed-20-dimensionality MELODIC maps. Stage-1
timecourses are design-normalized; no randomise permutations are run.
USAGE
}

dimension="${1:-}"
if [[ -z "$dimension" || "$dimension" == "--help" || "$dimension" == "-h" ]]; then
    usage
    [[ "$dimension" == "--help" || "$dimension" == "-h" ]] && exit 0
    exit 1
fi
shift

case "$dimension" in
    0) dimension_label="00" ;;
    20) dimension_label="20" ;;
    *) echo "ERROR: Dimensionality must be 0 or 20." >&2; usage >&2; exit 1 ;;
esac

dryrun=0
while (($#)); do
    case "$1" in
        --dry-run|--render-only) dryrun=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *) echo "ERROR: Unknown argument: $1" >&2; usage >&2; exit 1 ;;
    esac
done

scriptdir="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
maindir="$(dirname "$scriptdir")"
derivdir="${DERIVATIVES_ROOT:-${maindir}/derivatives}"
fsldir="${FSL_OUTPUT_DIR:-${derivdir}/fsl}"
task="${TASK_ID:-rest}"
inputlist="${DUAL_REGRESSION_FILELIST:-${fsldir}/melodic_filelist_5mm_denoised.txt}"
melodicdir="${MELODIC_OUTPUT_DIR:-${fsldir}/melodic-concat_denoised_dim-${dimension_label}_task-${task}.ica}"
melodic_ic="${melodicdir}/melodic_IC.nii.gz"
outputdir="${DUAL_REGRESSION_OUTPUT_DIR:-${fsldir}/dual-regression_denoised_dim-${dimension_label}_task-${task}.dr}"

printf 'Dimensionality: %s\n' "$dimension" >&2
printf 'Input list: %s\n' "$inputlist" >&2
printf 'Group maps: %s\n' "$melodic_ic" >&2
printf 'Output: %s\n' "$outputdir" >&2
printf 'Dual regression: %s 1 -1 0 %s <ordered inputs>\n' \
    "$melodic_ic" "$outputdir" >&2

if ((dryrun)); then
    exit 0
fi

command -v fslnvols >/dev/null 2>&1 || { echo "ERROR: fslnvols is not on PATH." >&2; exit 1; }
[[ -n "${FSLDIR:-}" && -x "${FSLDIR}/bin/fsl_sub" ]] || {
    echo "ERROR: FSLDIR is not configured with an executable fsl_sub." >&2
    exit 1
}
[[ -f "$inputlist" ]] || { echo "ERROR: Input list not found: $inputlist" >&2; exit 1; }
[[ -f "$melodic_ic" ]] || { echo "ERROR: Group MELODIC maps not found: $melodic_ic" >&2; exit 1; }
[[ ! -e "$outputdir" ]] || { echo "ERROR: Output already exists: $outputdir" >&2; exit 1; }

inputs=()
while IFS= read -r input || [[ -n "$input" ]]; do
    [[ -z "$input" ]] && continue
    [[ -f "$input" ]] || { echo "ERROR: Input not found: $input" >&2; exit 1; }
    inputs+=("$input")
done < "$inputlist"
((${#inputs[@]} > 0)) || { echo "ERROR: Input list is empty: $inputlist" >&2; exit 1; }

ncomponents="$(fslnvols "$melodic_ic")"
[[ "$ncomponents" =~ ^[1-9][0-9]*$ ]] || {
    echo "ERROR: Could not determine the number of MELODIC components." >&2
    exit 1
}
printf 'Input runs: %d\n' "${#inputs[@]}" >&2
printf 'Group components: %d\n' "$ncomponents" >&2

"${scriptdir}/dual_regression" \
    "$melodic_ic" \
    1 -1 0 \
    "$outputdir" \
    "${inputs[@]}"

mapping="${outputdir}/input_order.tsv"
printf 'dual_regression_index\tdual_regression_label\tparticipant\trun\tcondition\tcondition_order\tfile\n' >"$mapping"
for index in "${!inputs[@]}"; do
    name="$(basename "${inputs[$index]}")"
    participant="unknown"
    run="unknown"
    condition="unknown"
    condition_order="unknown"
    [[ "$name" =~ ^(sub-[^_]+) ]] && participant="${BASH_REMATCH[1]}"
    [[ "$name" =~ _run-([^_]+) ]] && run="${BASH_REMATCH[1]}"
    [[ "$name" =~ _condition-([^_]+) ]] && condition="${BASH_REMATCH[1]}"
    [[ "$name" =~ _order-([^_]+) ]] && condition_order="${BASH_REMATCH[1]}"
    printf '%d\tsubject%05d\t%s\t%s\t%s\t%s\t%s\n' \
        "$index" "$index" "$participant" "$run" "$condition" \
        "$condition_order" "${inputs[$index]}" >>"$mapping"
done
echo "Wrote $mapping" >&2
