#!/usr/bin/env bash
set -euo pipefail

# Run standard FSL dual regression with the original Smith09 network maps.

usage() {
    cat <<'USAGE'
Usage: code/run_dual_regression_smith09.sh {smoothed|denoised} [--dry-run]

Resample the 10 Smith09 maps to the analysis grid and run stages 1 and 2 of
the original FSL dual_regression script. No randomise permutations are run.
USAGE
}

data_set="${1:-}"
if [[ -z "$data_set" || "$data_set" == "--help" || "$data_set" == "-h" ]]; then
    usage
    [[ "$data_set" == "--help" || "$data_set" == "-h" ]] && exit 0
    exit 1
fi
shift

case "$data_set" in
    smoothed) filelist_name="melodic_filelist_5mm.txt" ;;
    denoised) filelist_name="melodic_filelist_5mm_denoised.txt" ;;
    *) echo "ERROR: Data set must be smoothed or denoised." >&2; usage >&2; exit 1 ;;
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
inputlist="${DUAL_REGRESSION_FILELIST:-${fsldir}/${filelist_name}}"
smith_maps="${SMITH09_MAPS:-${maindir}/masks/PNAS_Smith09_rsn10.nii.gz}"
reference_dir="${SMITH09_REFERENCE_DIR:-${fsldir}/smith09_reference}"
resampled_maps="${reference_dir}/PNAS_Smith09_rsn10_resampled.nii.gz"
outputdir="${DUAL_REGRESSION_OUTPUT_DIR:-${fsldir}/dual-regression_smith09_${data_set}.dr}"
scratchroot="${WORK_ROOT:-/ZPOOL/data/scratch/${USER:-$(whoami)}}"

printf 'Data set: %s\n' "$data_set" >&2
printf 'Input list: %s\n' "$inputlist" >&2
printf 'Smith09 maps: %s\n' "$smith_maps" >&2
printf 'Resampled maps: %s\n' "$resampled_maps" >&2
printf 'Output: %s\n' "$outputdir" >&2
printf 'Dual regression: %s 1 -1 0 %s <ordered inputs>\n' \
    "$resampled_maps" "$outputdir" >&2

if ((dryrun)); then
    exit 0
fi

for command in 3dinfo fslmaths fslmerge fslroi fslnvols fslsplit flirt; do
    command -v "$command" >/dev/null 2>&1 || {
        echo "ERROR: $command is not on PATH." >&2
        exit 1
    }
done
[[ -n "${FSLDIR:-}" && -x "${FSLDIR}/bin/fsl_sub" ]] || {
    echo "ERROR: FSLDIR is not configured with an executable fsl_sub." >&2
    exit 1
}
[[ -f "$inputlist" ]] || { echo "ERROR: Input list not found: $inputlist" >&2; exit 1; }
[[ -f "$smith_maps" ]] || { echo "ERROR: Smith09 maps not found: $smith_maps" >&2; exit 1; }
[[ ! -e "$outputdir" ]] || { echo "ERROR: Output already exists: $outputdir" >&2; exit 1; }

inputs=()
while IFS= read -r input || [[ -n "$input" ]]; do
    [[ -z "$input" ]] && continue
    [[ -f "$input" ]] || { echo "ERROR: Input not found: $input" >&2; exit 1; }
    inputs+=("$input")
done < "$inputlist"
((${#inputs[@]} > 0)) || { echo "ERROR: Input list is empty: $inputlist" >&2; exit 1; }
printf 'Input runs: %d\n' "${#inputs[@]}" >&2

reference="${inputs[0]}"
reference_match=""
if [[ -f "$resampled_maps" ]]; then
    reference_match="$(3dinfo -same_grid "$resampled_maps" "$reference" | tr -d '[:space:]')"
fi

if [[ "$reference_match" != "11" || "$(fslnvols "$resampled_maps" 2>/dev/null || true)" != "10" ]]; then
    mkdir -p "$reference_dir" "${scratchroot}/r21-rest"
    workdir="$(mktemp -d "${scratchroot}/r21-rest/smith09_reference.XXXXXX")"
    cleanup() { rm -rf "$workdir"; }
    trap cleanup EXIT

    reference_volume="${workdir}/reference.nii.gz"
    fslroi "$reference" "$reference_volume" 0 1
    fslsplit "$smith_maps" "${workdir}/smith" -t

    resampled_parts=()
    for map in "${workdir}"/smith????.nii.gz; do
        number="${map##*smith}"
        number="${number%.nii.gz}"
        resampled="${workdir}/rsmith${number}.nii.gz"
        flirt \
            -in "$map" \
            -ref "$reference_volume" \
            -applyxfm \
            -usesqform \
            -interp trilinear \
            -out "$resampled"
        resampled_parts+=("$resampled")
    done
    ((${#resampled_parts[@]} == 10)) || {
        echo "ERROR: Expected 10 Smith09 maps; found ${#resampled_parts[@]}" >&2
        exit 1
    }
    fslmerge -t "${workdir}/smith09_merged.nii.gz" "${resampled_parts[@]}"
    fslmaths "${workdir}/smith09_merged.nii.gz" -nan "$resampled_maps"
fi

[[ "$(fslnvols "$resampled_maps")" == "10" ]] || {
    echo "ERROR: Resampled Smith09 image does not contain 10 maps." >&2
    exit 1
}
[[ "$(3dinfo -same_grid "$resampled_maps" "$reference" | tr -d '[:space:]')" == "11" ]] || {
    echo "ERROR: Resampled Smith09 maps do not match the input grid." >&2
    exit 1
}

"${scriptdir}/dual_regression" \
    "$resampled_maps" \
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
