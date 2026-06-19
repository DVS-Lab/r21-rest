#!/usr/bin/env bash
set -euo pipefail

# Run the MRIQC group report after participant-level MRIQC has completed.
#
# Usage:
#   bash code/mriqc_group.sh
#   bash code/mriqc_group.sh --dry-run

usage() {
    cat <<'USAGE'
Usage: code/mriqc_group.sh [--dry-run]

Run the MRIQC group report after participant-level MRIQC has completed.
USAGE
}

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

projectname="r21-rest"
bidsdir="${BIDS_DIR:-/ZPOOL/data/projects/r21-cardgame/bids}"
derivdir="${DERIVATIVES_ROOT:-${maindir}/derivatives}"
outputdir="${MRIQC_OUTPUT_DIR:-${derivdir}/mriqc}"
scratchroot="${WORK_ROOT:-/ZPOOL/data/scratch/${USER:-$(whoami)}}"
workdir="${MRIQC_GROUP_WORK_DIR:-${scratchroot}/mriqc/group}"

mriqc_image="${MRIQC_IMAGE:-/ZPOOL/data/tools/mriqc-24.0.2.sif}"
templateflow_dir="${TEMPLATEFLOW_DIR:-/ZPOOL/data/tools/templateflow}"
mplconfigdir="${MPLCONFIGDIR:-${scratchroot}/mplconfigdir}"

modalities="${MRIQC_MODALITIES:-T1w bold}"
read -r -a modalities_array <<< "$modalities"

if command -v apptainer >/dev/null 2>&1; then
    runtime="apptainer"
elif command -v singularity >/dev/null 2>&1; then
    runtime="singularity"
elif [[ "$dryrun" -eq 1 ]]; then
    runtime="apptainer"
else
    echo "ERROR: Could not find apptainer or singularity on PATH." >&2
    exit 1
fi

cmd=(
    "$runtime" run --cleanenv
    -B "${bidsdir}:/data:ro"
    -B "${outputdir}:/out"
    -B "${workdir}:/workdir"
    -B "${templateflow_dir}:/templateflow"
    -B "${mplconfigdir}:/mplconfigdir"
    --env "TEMPLATEFLOW_HOME=/templateflow"
    --env "MPLCONFIGDIR=/mplconfigdir"
    "$mriqc_image"
    /data
    /out
    group
    --modalities "${modalities_array[@]}"
    -w /workdir
)

printf 'Project: %s\n' "$projectname" >&2
printf 'BIDS: %s\n' "$bidsdir" >&2
printf 'Output: %s\n' "$outputdir" >&2
printf 'Scratch: %s\n' "$workdir" >&2
printf 'Modalities: %s\n' "$modalities" >&2

printf 'Command:\n' >&2
printf '%q ' "${cmd[@]}" >&2
printf '\n' >&2

if [[ "$dryrun" -eq 1 ]]; then
    exit 0
fi

[[ -d "$bidsdir" ]] || { echo "ERROR: BIDS directory not found: $bidsdir" >&2; exit 1; }
[[ -d "$outputdir" ]] || { echo "ERROR: MRIQC output directory not found: $outputdir" >&2; exit 1; }
[[ -f "$mriqc_image" ]] || { echo "ERROR: MRIQC image not found: $mriqc_image" >&2; exit 1; }
[[ -d "$templateflow_dir" ]] || { echo "ERROR: TemplateFlow directory not found: $templateflow_dir" >&2; exit 1; }
if [[ ! -w "$templateflow_dir" ]]; then
    echo "WARNING: TemplateFlow directory is not writable: $templateflow_dir" >&2
    echo "WARNING: If MRIQC needs a missing template, set TEMPLATEFLOW_DIR to a writable cache." >&2
fi

mkdir -p "$workdir" "$mplconfigdir"

"${cmd[@]}"
