#!/usr/bin/env bash
set -euo pipefail

# Prepare and run the four Smith09-plus-reward PPI component tests.

usage() {
    cat <<'USAGE'
Usage: code/run_smith09_ppi_randomise.sh [all|dmn-ecn|dmn-reward|dmn-left-fpn|dmn-right-fpn] [options]

Build component-12 condition differences for completed PPI stage-2 outputs and
launch their one-sample randomise jobs in parallel.

Options:
  --max-jobs N              Concurrent randomise jobs (default: 35)
  --contrasts LIST          Comma-separated contrasts or all (default: all)
  --n-perm N                Permutations per job (default: 5000)
  --cluster-threshold VALUE Cluster-forming t threshold (default: 3.1)
  --tfce                     Also calculate TFCE (default: off)
  --dry-run                  Print the launch plan only
USAGE
}

ppi_set="all"
if (($#)) && [[ "$1" != --* ]]; then
    ppi_set="$1"
    shift
fi
case "$ppi_set" in
    all|dmn-ecn|dmn-reward|dmn-left-fpn|dmn-right-fpn) ;;
    *) echo "ERROR: Unknown PPI analysis: $ppi_set" >&2; usage >&2; exit 1 ;;
esac

maxjobs="${RANDOMISE_MAX_JOBS:-35}"
contrast_selection="all"
nperm="${N_PERM:-5000}"
cluster_threshold="${CLUSTER_THRESHOLD:-3.1}"
tfce=0
dryrun=0
while (($#)); do
    case "$1" in
        --max-jobs) maxjobs="${2:-}"; shift 2 ;;
        --contrasts) contrast_selection="${2:-}"; shift 2 ;;
        --n-perm) nperm="${2:-}"; shift 2 ;;
        --cluster-threshold) cluster_threshold="${2:-}"; shift 2 ;;
        --tfce) tfce=1; shift ;;
        --dry-run|--render-only) dryrun=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *) echo "ERROR: Unknown argument: $1" >&2; usage >&2; exit 1 ;;
    esac
done
[[ "$maxjobs" =~ ^[1-9][0-9]*$ ]] || { echo "ERROR: --max-jobs must be positive." >&2; exit 1; }
[[ "$nperm" =~ ^[1-9][0-9]*$ ]] || { echo "ERROR: --n-perm must be positive." >&2; exit 1; }
[[ "$cluster_threshold" =~ ^[0-9]+([.][0-9]+)?$ ]] || {
    echo "ERROR: --cluster-threshold must be nonnegative numeric value." >&2
    exit 1
}

if [[ "$ppi_set" == "all" ]]; then
    ppis=(dmn-ecn dmn-reward dmn-left-fpn dmn-right-fpn)
else
    ppis=("$ppi_set")
fi
all_contrasts=(
    both-minus-sham
    both-minus-rtpj
    both-minus-vlpfc
    rtpj-minus-vlpfc
    rtpj-minus-sham
    vlpfc-minus-sham
    both-minus-mean-rtpj-vlpfc
    mean-stimulation-minus-sham
)
contrasts=()
if [[ "$contrast_selection" == "all" ]]; then
    contrasts=("${all_contrasts[@]}")
else
    IFS=',' read -r -a requested_contrasts <<<"$contrast_selection"
    for contrast in "${requested_contrasts[@]}"; do
        valid=0
        for known in "${all_contrasts[@]}"; do
            [[ "$contrast" == "$known" ]] && valid=1
        done
        ((valid)) || { echo "ERROR: Unknown contrast: $contrast" >&2; exit 1; }
        contrasts+=("$contrast")
    done
fi
((${#contrasts[@]} > 0)) || { echo "ERROR: Select at least one contrast." >&2; exit 1; }

scriptdir="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
maindir="$(dirname "$scriptdir")"
derivdir="${DERIVATIVES_ROOT:-${maindir}/derivatives}"
fsldir="${FSL_OUTPUT_DIR:-${derivdir}/fsl}"
component=12
component_padded="0012"
contrast_csv="$(IFS=','; echo "${contrasts[*]}")"
job_count=$((${#ppis[@]} * ${#contrasts[@]}))

printf 'PPI analyses: %s\n' "${ppis[*]}" >&2
printf 'Component: 12; contrasts: %s\n' "${contrasts[*]}" >&2
printf 'Randomise jobs: %d; maximum concurrent: %d\n' "$job_count" "$maxjobs" >&2
printf 'Permutations: %d; TFCE: %s; cluster threshold: %s\n' \
    "$nperm" "$([[ "$tfce" == 1 ]] && echo yes || echo no)" "$cluster_threshold" >&2

for ppi in "${ppis[@]}"; do
    drdir="${fsldir}/dual-regression_smith09-reward_denoised_ppi-${ppi}.dr"
    component_dir="${drdir}/contrasts/component-${component_padded}_stat-beta"
    args=(smith09-reward "$component" --output-dir "$component_dir" --contrasts "$contrast_csv")
    [[ -d "$component_dir" ]] && args+=(--resume)
    ((dryrun)) && args+=(--dry-run)
    DUAL_REGRESSION_DIR="$drdir" bash "${scriptdir}/make_dual_regression_contrasts.sh" "${args[@]}"
done

if ((dryrun)); then
    for ppi in "${ppis[@]}"; do
        for contrast in "${contrasts[@]}"; do
            printf 'JOB ppi=%s component=12 contrast=%s nperm=%s -c %s\n' \
                "$ppi" "$contrast" "$nperm" "$cluster_threshold" >&2
        done
    done
    exit 0
fi

logdir="${derivdir}/logs/randomise/smith09-reward-ppi"
mkdir -p "$logdir"
tfce_args=()
((tfce)) && tfce_args=(--tfce)
pids=()
failures=0
launched=0
for ppi in "${ppis[@]}"; do
    drdir="${fsldir}/dual-regression_smith09-reward_denoised_ppi-${ppi}.dr"
    component_dir="${drdir}/contrasts/component-${component_padded}_stat-beta"
    network="dmn-x-${ppi#dmn-}"
    for contrast in "${contrasts[@]}"; do
        while [[ "$(jobs -rp | wc -l | tr -d ' ')" -ge "$maxjobs" ]]; do sleep 2; done
        logfile="${logdir}/ppi-${ppi}_contrast-${contrast}.log"
        echo "Launching ${ppi} ${contrast}; log: $logfile" >&2
        DUAL_REGRESSION_DIR="$drdir" CONTRAST_COMPONENT_DIR="$component_dir" \
            bash "${scriptdir}/randomise.sh" smith09-reward "$network" "$component" "$contrast" \
            --n-perm "$nperm" --cluster-threshold "$cluster_threshold" \
            "${tfce_args[@]}" >"$logfile" 2>&1 &
        pids+=("$!")
        launched=$((launched + 1))
    done
done

for pid in "${pids[@]}"; do
    if ! wait "$pid"; then failures=1; fi
done
if ((failures)); then
    echo "ERROR: One or more PPI randomise jobs failed. Check $logdir" >&2
    exit 1
fi
echo "PPI randomise jobs completed successfully: $launched" >&2
