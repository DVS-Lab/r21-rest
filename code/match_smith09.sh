#!/usr/bin/env bash
set -euo pipefail

# Resample the original Smith09 maps and match them to group MELODIC components.

usage() {
    cat <<'USAGE'
Usage: code/match_smith09.sh {smoothed|denoised} {0|20} [--dry-run]

Match one completed group MELODIC analysis to the original Smith09 10-network
maps. Signed correlations are retained; matches are ranked by absolute value.
USAGE
}

data_set="${1:-}"
dimension="${2:-}"
if [[ -z "$data_set" || "$data_set" == "--help" || "$data_set" == "-h" ]]; then
    usage
    [[ "$data_set" == "--help" || "$data_set" == "-h" ]] && exit 0
    exit 1
fi

case "$data_set" in
    smoothed) melodic_label=""; output_label="" ;;
    denoised) melodic_label="_denoised"; output_label="_denoised" ;;
    *) echo "ERROR: Data set must be smoothed or denoised." >&2; usage >&2; exit 1 ;;
esac

case "$dimension" in
    0) dimension_label="00" ;;
    20) dimension_label="20" ;;
    *) echo "ERROR: Dimensionality must be 0 or 20." >&2; usage >&2; exit 1 ;;
esac
shift 2

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
melodicdir="${MELODIC_OUTPUT_DIR:-${fsldir}/melodic-concat${melodic_label}_dim-${dimension_label}_task-${task}.ica}"
melodic_ic="${melodicdir}/melodic_IC.nii.gz"
melodic_mask="${MELODIC_MASK:-${melodicdir}/mask.nii.gz}"
smith_maps="${SMITH09_MAPS:-${maindir}/masks/PNAS_Smith09_rsn10.nii.gz}"
outputdir="${SMITH09_OUTPUT_DIR:-${fsldir}/smith09${output_label}_dim-${dimension_label}_task-${task}}"
scratchroot="${WORK_ROOT:-/ZPOOL/data/scratch/${USER:-$(whoami)}}"

printf 'Data set: %s\n' "$data_set" >&2
printf 'MELODIC components: %s\n' "$melodic_ic" >&2
printf 'MELODIC mask: %s\n' "$melodic_mask" >&2
printf 'Smith09 maps: %s\n' "$smith_maps" >&2
printf 'Output: %s\n' "$outputdir" >&2

if ((dryrun)); then
    cat >&2 <<EOF
Commands: fslroi, fslsplit, flirt -applyxfm -usesqform, fslmerge, fslmaths,
          fslcc -t -1 --noabs, gen_fslcc_table.py
EOF
    exit 0
fi

for command in fslroi fslsplit flirt fslmerge fslmaths fslcc; do
    command -v "$command" >/dev/null 2>&1 || { echo "ERROR: $command is not on PATH." >&2; exit 1; }
done
[[ -f "$melodic_ic" ]] || { echo "ERROR: MELODIC components not found: $melodic_ic" >&2; exit 1; }
[[ -f "$melodic_mask" ]] || { echo "ERROR: MELODIC mask not found: $melodic_mask" >&2; exit 1; }
[[ -f "$smith_maps" ]] || { echo "ERROR: Smith09 maps not found: $smith_maps" >&2; exit 1; }

mkdir -p "$outputdir" "${scratchroot}/r21-rest"
workdir="$(mktemp -d "${scratchroot}/r21-rest/smith09_${data_set}_dim-${dimension_label}.XXXXXX")"
cleanup() {
    rm -rf "$workdir"
}
trap cleanup EXIT

reference="${workdir}/melodic_reference.nii.gz"
fslroi "$melodic_ic" "$reference" 0 1
fslsplit "$smith_maps" "${workdir}/smith" -t

resampled_maps=()
for map in "${workdir}"/smith????.nii.gz; do
    number="${map##*smith}"
    number="${number%.nii.gz}"
    resampled="${workdir}/rsmith${number}.nii.gz"
    flirt \
        -in "$map" \
        -ref "$reference" \
        -applyxfm \
        -usesqform \
        -interp trilinear \
        -out "$resampled"
    resampled_maps+=("$resampled")
done

((${#resampled_maps[@]} == 10)) || {
    echo "ERROR: Expected 10 Smith09 maps; found ${#resampled_maps[@]}" >&2
    exit 1
}

resampled_merged="${outputdir}/PNAS_Smith09_rsn10_resampled.nii.gz"
fslmerge -t "${workdir}/smith09_merged.nii.gz" "${resampled_maps[@]}"
fslmaths "${workdir}/smith09_merged.nii.gz" -nan "$resampled_merged"

fslcc_output="${outputdir}/fslcc_output.txt"
fslcc -t -1 --noabs -m "$melodic_mask" "$melodic_ic" "$resampled_merged" >"$fslcc_output"
python3 "${scriptdir}/gen_fslcc_table.py" --input "$fslcc_output" --output-dir "$outputdir"
