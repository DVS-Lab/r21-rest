#!/usr/bin/env bash
set -euo pipefail

# Build and run the final Smith09 DMN x ECN PPI condition contrasts.

usage() {
    cat <<'USAGE'
Usage: code/run_smith09_dmn_ecn_ppi_randomise.sh [options]

Build component-11 condition differences from the completed 10-map Smith09
DMN x ECN PPI stage-2 outputs, then run one-sample randomise tests.

Options:
  --contrasts LIST          Comma-separated contrasts (default: final three)
  --n-perm N                Permutations per job (default: 5000)
  --cluster-threshold VALUE Cluster-forming t threshold (default: 3.1)
  --tfce                     Also calculate TFCE (default: off)
  --dry-run                  Print resolved paths and planned contrasts only

The default contrasts are mean stimulation minus sham, BOTH minus the mean of
the two single-site conditions, and RTPJ minus VLPFC.
USAGE
}

contrasts="${PPI_CONTRASTS:-mean-stimulation-minus-sham,both-minus-mean-rtpj-vlpfc,rtpj-minus-vlpfc}"
nperm="${N_PERM:-5000}"
cluster_threshold="${CLUSTER_THRESHOLD:-3.1}"
tfce=0
dryrun=0
while (($#)); do
    case "$1" in
        --contrasts) contrasts="${2:-}"; shift 2 ;;
        --n-perm) nperm="${2:-}"; shift 2 ;;
        --cluster-threshold) cluster_threshold="${2:-}"; shift 2 ;;
        --tfce) tfce=1; shift ;;
        --dry-run|--render-only) dryrun=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *) echo "ERROR: Unknown argument: $1" >&2; usage >&2; exit 1 ;;
    esac
done

[[ "$nperm" =~ ^[1-9][0-9]*$ ]] || { echo "ERROR: --n-perm must be positive." >&2; exit 1; }
[[ "$cluster_threshold" =~ ^[0-9]+([.][0-9]+)?$ ]] || {
    echo "ERROR: --cluster-threshold must be nonnegative numeric value." >&2
    exit 1
}

scriptdir="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
maindir="$(dirname "$scriptdir")"
derivdir="${DERIVATIVES_ROOT:-${maindir}/derivatives}"
fsldir="${FSL_OUTPUT_DIR:-${derivdir}/fsl}"
drdir="${PPI_DUAL_REGRESSION_DIR:-${fsldir}/dual-regression_smith09_denoised_ppi-dmn-ecn.dr}"
component_dir="${drdir}/contrasts/component-0011_stat-beta"

printf 'PPI dual regression: %s\n' "$drdir" >&2
printf 'Component: 11 (DMN x ECN)\n' >&2
printf 'Contrasts: %s\n' "$contrasts" >&2
printf 'Permutations: %s; TFCE: %s; cluster threshold: %s\n' \
    "$nperm" "$([[ "$tfce" == 1 ]] && echo yes || echo no)" "$cluster_threshold" >&2

make_args=(smith09 11 --output-dir "$component_dir" --contrasts "$contrasts")
[[ -d "$component_dir" ]] && make_args+=(--resume)
((dryrun)) && make_args+=(--dry-run)
DUAL_REGRESSION_DIR="$drdir" bash "${scriptdir}/make_dual_regression_contrasts.sh" "${make_args[@]}"

((dryrun)) && exit 0

runner="${component_dir}/run_randomise.sh"
[[ -x "$runner" ]] || { echo "ERROR: Randomise launcher not found: $runner" >&2; exit 1; }
N_PERM="$nperm" CLUSTER_THRESHOLD="$cluster_threshold" TFCE="$tfce" "$runner"

echo "DMN x ECN PPI randomise contrasts completed successfully." >&2
