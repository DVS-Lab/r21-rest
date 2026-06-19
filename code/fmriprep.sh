#!/usr/bin/env bash
set -euo pipefail

# Run fMRIPrep for one participant.
#
# Usage:
#   bash code/fmriprep.sh 189
#   bash code/fmriprep.sh sub-189 --dry-run

usage() {
    cat <<'USAGE'
Usage: code/fmriprep.sh SUBJECT [--dry-run]

Run fMRIPrep for one participant. SUBJECT may be written as 189 or sub-189.
USAGE
}

dryrun=0
sub="${1:-}"
if [[ -z "$sub" || "$sub" == "--help" || "$sub" == "-h" ]]; then
    usage
    exit 0
fi
shift || true

while (($#)); do
    case "$1" in
        --dry-run|--render-only) dryrun=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *) echo "ERROR: Unknown argument: $1" >&2; usage >&2; exit 1 ;;
    esac
done

sub="${sub#sub-}"
if [[ ! "$sub" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]]; then
    echo "ERROR: Invalid participant label: $sub" >&2
    exit 1
fi

scriptdir="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
maindir="$(dirname "$scriptdir")"

projectname="r21-rest"
bidsdir="${BIDS_DIR:-/ZPOOL/data/projects/r21-cardgame/bids}"
derivdir="${DERIVATIVES_ROOT:-${maindir}/derivatives}"
outputdir="${FMRIPREP_OUTPUT_DIR:-${derivdir}/fmriprep-25.2.5}"
scratchdir="${WORK_ROOT:-/ZPOOL/data/scratch/${USER:-$(whoami)}}"

fmriprep_image="${FMRIPREP_IMAGE:-/ZPOOL/data/tools/fmriprep-25.2.5.sif}"
templateflow_dir="${TEMPLATEFLOW_DIR:-/ZPOOL/data/tools/templateflow}"
fs_license="${FS_LICENSE:-/ZPOOL/data/tools/licenses/fs_license.txt}"

task_id="${TASK_ID:-rest}"
nthreads="${FMRIPREP_NPROCS:-8}"
omp_nthreads="${FMRIPREP_OMP_NTHREADS:-4}"
mem_mb="${FMRIPREP_MEM_MB:-24000}"
cifti_density="${CIFTI_DENSITY:-91k}"
output_spaces="${FMRIPREP_OUTPUT_SPACES:-fsLR fsaverage MNI152NLin6Asym MNI152NLin2009cAsym}"
read -r -a output_spaces_array <<< "$output_spaces"

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
    -B "${bidsdir}:/input:ro"
    -B "${derivdir}:/output"
    -B "${scratchdir}:/scratch"
    -B "${templateflow_dir}:/opt/templateflow:ro"
    -B "$(dirname "$fs_license"):/opts:ro"
    --env "TEMPLATEFLOW_HOME=/opt/templateflow"
    --env "FS_LICENSE=/opts/$(basename "$fs_license")"
    "$fmriprep_image"
    /input
    "/output/$(basename "$outputdir")"
    participant
    --participant-label "$sub"
    --task-id "$task_id"
    --stop-on-first-crash
    --nthreads "$nthreads"
    --omp-nthreads "$omp_nthreads"
    --mem-mb "$mem_mb"
    --output-spaces "${output_spaces_array[@]}"
    --cifti-output "$cifti_density"
    --skip-bids-validation
    --fs-license-file "/opts/$(basename "$fs_license")"
    --fs-subjects-dir /output/freesurfer
    --notrack
    -w /scratch
)

printf 'Project: %s\n' "$projectname" >&2
printf 'Subject: sub-%s\n' "$sub" >&2
printf 'BIDS: %s\n' "$bidsdir" >&2
printf 'Output: %s\n' "$outputdir" >&2
printf 'Scratch: %s\n' "$scratchdir" >&2

printf 'Command:\n' >&2
printf '%q ' "${cmd[@]}" >&2
printf '\n' >&2

if [[ "$dryrun" -eq 1 ]]; then
    exit 0
fi

[[ -d "$bidsdir" ]] || { echo "ERROR: BIDS directory not found: $bidsdir" >&2; exit 1; }
[[ -f "$fmriprep_image" ]] || { echo "ERROR: fMRIPrep image not found: $fmriprep_image" >&2; exit 1; }
[[ -d "$templateflow_dir" ]] || { echo "ERROR: TemplateFlow directory not found: $templateflow_dir" >&2; exit 1; }
[[ -f "$fs_license" ]] || { echo "ERROR: FreeSurfer license not found: $fs_license" >&2; exit 1; }

mkdir -p "$outputdir" "${derivdir}/freesurfer" "$scratchdir"

"${cmd[@]}"
