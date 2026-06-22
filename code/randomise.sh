#!/usr/bin/env bash
set -euo pipefail

# Run one one-sample randomise test for one ICA component and condition contrast.

usage() {
    cat <<'USAGE'
Usage: code/randomise.sh {smith09|0|20} NETWORK COMPONENT CONTRAST [options]

Run one randomise job on a component-wise condition-difference image prepared
by make_dual_regression_contrasts.sh.

Options:
  --map-type {beta|z}       Stage-2 map type (default: beta)
  --n-perm N                Permutations (default: 5000)
  --cluster-threshold VALUE Cluster-forming t threshold (default: 3.1)
  --dry-run                  Print the resolved command only
USAGE
}

analysis="${1:-}"
network="${2:-}"
component="${3:-}"
contrast="${4:-}"
if [[ -z "$analysis" || "$analysis" == "--help" || "$analysis" == "-h" ]]; then
    usage
    [[ "$analysis" == "--help" || "$analysis" == "-h" ]] && exit 0
    exit 1
fi
if [[ -z "$network" || -z "$component" || -z "$contrast" ]]; then
    echo "ERROR: NETWORK, COMPONENT, and CONTRAST are required." >&2
    usage >&2
    exit 1
fi
shift 4

case "$analysis" in
    smith09) analysis_label="smith09_denoised" ;;
    0) analysis_label="denoised_dim-00_task-rest" ;;
    20) analysis_label="denoised_dim-20_task-rest" ;;
    *) echo "ERROR: Analysis must be smith09, 0, or 20." >&2; usage >&2; exit 1 ;;
esac
[[ "$network" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || {
    echo "ERROR: NETWORK must contain only lowercase letters, numbers, _ or -." >&2
    exit 1
}
[[ "$component" =~ ^[1-9][0-9]*$ ]] || {
    echo "ERROR: COMPONENT must be a positive 1-based integer." >&2
    exit 1
}
case "$contrast" in
    both-minus-sham|both-minus-rtpj|both-minus-vlpfc|rtpj-minus-vlpfc|rtpj-minus-sham|vlpfc-minus-sham|both-minus-mean-rtpj-vlpfc) ;;
    *) echo "ERROR: Unknown condition contrast: $contrast" >&2; exit 1 ;;
esac

map_type="beta"
nperm="${N_PERM:-5000}"
cluster_threshold="${CLUSTER_THRESHOLD:-3.1}"
dryrun=0
while (($#)); do
    case "$1" in
        --map-type) map_type="${2:-}"; shift 2 ;;
        --n-perm) nperm="${2:-}"; shift 2 ;;
        --cluster-threshold) cluster_threshold="${2:-}"; shift 2 ;;
        --dry-run|--render-only) dryrun=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *) echo "ERROR: Unknown argument: $1" >&2; usage >&2; exit 1 ;;
    esac
done

case "$map_type" in
    beta|z) ;;
    *) echo "ERROR: --map-type must be beta or z." >&2; exit 1 ;;
esac
[[ "$nperm" =~ ^[1-9][0-9]*$ ]] || {
    echo "ERROR: --n-perm must be a positive integer." >&2
    exit 1
}
[[ "$cluster_threshold" =~ ^[0-9]+([.][0-9]+)?$ ]] || {
    echo "ERROR: --cluster-threshold must be nonnegative numeric value." >&2
    exit 1
}

scriptdir="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
maindir="$(dirname "$scriptdir")"
derivdir="${DERIVATIVES_ROOT:-${maindir}/derivatives}"
fsldir="${FSL_OUTPUT_DIR:-${derivdir}/fsl}"
task="${TASK_ID:-rest}"
drdir="${DUAL_REGRESSION_DIR:-${fsldir}/dual-regression_${analysis_label}.dr}"
component_padded="$(printf '%04d' "$component")"
component_dir="${CONTRAST_COMPONENT_DIR:-${drdir}/contrasts/component-${component_padded}_stat-${map_type}}"
group_input="${component_dir}/${contrast}/group_task-${task}_component-${component_padded}_stat-${map_type}_contrast-${contrast}.nii.gz"
mask="${DUAL_REGRESSION_MASK:-${drdir}/mask.nii.gz}"
design_mat="${component_dir}/design.mat"
design_con="${component_dir}/design.con"
design_grp="${component_dir}/design.grp"
outputdir="${RANDOMISE_OUTPUT_DIR:-${component_dir}/randomise/network-${network}}"
output_prefix="${outputdir}/task-${task}_network-${network}_component-${component_padded}_stat-${map_type}_contrast-${contrast}"
complete_marker="${output_prefix}.complete"

cmd=(
    randomise
    -i "$group_input"
    -o "$output_prefix"
    -m "$mask"
    -d "$design_mat"
    -t "$design_con"
    -e "$design_grp"
    -n "$nperm"
    -T
    -c "$cluster_threshold"
)

printf 'Analysis: %s\n' "$analysis" >&2
printf 'Network: %s; component: %d; contrast: %s\n' "$network" "$component" "$contrast" >&2
printf 'Input: %s\n' "$group_input" >&2
printf 'Output prefix: %s\n' "$output_prefix" >&2
printf 'Permutations: %s; TFCE: yes; cluster threshold: %s\n' "$nperm" "$cluster_threshold" >&2
printf 'Command:\n' >&2
printf '%q ' "${cmd[@]}" >&2
printf '\n' >&2

if ((dryrun)); then
    exit 0
fi
if [[ -f "$complete_marker" ]]; then
    echo "Already complete: $complete_marker" >&2
    exit 0
fi

command -v randomise >/dev/null 2>&1 || { echo "ERROR: randomise is not on PATH." >&2; exit 1; }
for required in "$group_input" "$mask" "$design_mat" "$design_con" "$design_grp"; do
    [[ -f "$required" ]] || { echo "ERROR: Required input not found: $required" >&2; exit 1; }
done

mkdir -p "$outputdir"
shopt -s nullglob
partial_outputs=("${output_prefix}"_*)
shopt -u nullglob
if ((${#partial_outputs[@]} > 0)); then
    echo "ERROR: Partial randomise outputs exist without a completion marker:" >&2
    printf '  %s\n' "${partial_outputs[@]}" >&2
    exit 1
fi

"${cmd[@]}"
{
    printf 'completed_utc\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'analysis\t%s\n' "$analysis"
    printf 'network\t%s\n' "$network"
    printf 'component\t%s\n' "$component"
    printf 'contrast\t%s\n' "$contrast"
    printf 'n_perm\t%s\n' "$nperm"
    printf 'cluster_threshold\t%s\n' "$cluster_threshold"
} >"$complete_marker"
echo "Completed: $output_prefix" >&2
