#!/usr/bin/env bash
set -euo pipefail

# Run temporal-concatenation group MELODIC at one requested dimensionality.

usage() {
    cat <<'USAGE'
Usage: code/melodic.sh {0|20} [--dry-run]

Run group MELODIC using derivatives/fsl/melodic_filelist_5mm.txt.
  0   Automatically estimate dimensionality
  20  Use a fixed dimensionality of 20
USAGE
}

dimension="${1:-}"
if [[ -z "$dimension" || "$dimension" == "--help" || "$dimension" == "-h" ]]; then
    usage
    exit 0
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
inputlist="${MELODIC_FILELIST:-${fsldir}/melodic_filelist_5mm.txt}"
outputdir="${MELODIC_OUTPUT_DIR:-${fsldir}/melodic-concat_dim-${dimension_label}_task-${task}.ica}"

cmd=(
    melodic
    -i "$inputlist"
    -o "$outputdir"
    -v
    --nobet
    --report
    --guireport=report.html
    -d "$dimension"
    --mmthresh=0.5
    --Ostats
    -a concat
)

printf 'Dimensionality: %s\n' "$dimension" >&2
printf 'Input list: %s\n' "$inputlist" >&2
printf 'Output: %s\n' "$outputdir" >&2
printf 'Command:\n' >&2
printf '%q ' "${cmd[@]}" >&2
printf '\n' >&2

if ((dryrun)); then
    exit 0
fi

command -v melodic >/dev/null 2>&1 || { echo "ERROR: melodic is not on PATH." >&2; exit 1; }
[[ -f "$inputlist" ]] || { echo "ERROR: MELODIC input list not found: $inputlist" >&2; exit 1; }
[[ ! -e "$outputdir" ]] || { echo "ERROR: Output already exists: $outputdir" >&2; exit 1; }

ninputs=0
while IFS= read -r input || [[ -n "$input" ]]; do
    [[ -z "$input" ]] && continue
    if [[ "$input" =~ [[:space:]] ]]; then
        echo "ERROR: File list must contain one path per nonblank line: $inputlist" >&2
        exit 1
    fi
    [[ -f "$input" ]] || { echo "ERROR: MELODIC input not found: $input" >&2; exit 1; }
    ((ninputs += 1))
done < "$inputlist"

((ninputs > 0)) || { echo "ERROR: MELODIC input list is empty: $inputlist" >&2; exit 1; }
printf 'Input runs: %d\n' "$ninputs" >&2

mkdir -p "$(dirname "$outputdir")"
"${cmd[@]}"
