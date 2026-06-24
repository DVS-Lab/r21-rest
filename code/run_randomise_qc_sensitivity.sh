#!/usr/bin/env bash
set -euo pipefail

# Run the documented differential-motion QC sensitivity analysis.

usage() {
    cat <<'USAGE'
Usage: code/run_randomise_qc_sensitivity.sh {primary|secondary|smith09|smith09-secondary|all} [options]

Exclude participants listed in code/exclude_qc_outliers.txt and write all
contrast inputs and randomise outputs under sensitivity-qc-outliers folders.

  primary  Data-derived primary ICA networks (49 jobs)
  secondary  Data-derived non-cerebellar secondary networks (63 jobs)
  smith09  Direct Smith09 primary maps (28 jobs)
  smith09-secondary  Direct non-cerebellar secondary maps (35 jobs)
  all      Run all four sets (175 jobs)
USAGE
}

analysis_set="${1:-}"
if [[ -z "$analysis_set" || "$analysis_set" == "--help" || "$analysis_set" == "-h" ]]; then
    usage
    [[ "$analysis_set" == "--help" || "$analysis_set" == "-h" ]] && exit 0
    exit 1
fi
shift
case "$analysis_set" in
    primary|secondary|smith09|smith09-secondary|all) ;;
    *) echo "ERROR: Unknown analysis set: $analysis_set" >&2; usage >&2; exit 1 ;;
esac

scriptdir="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
exclude_list="${scriptdir}/exclude_qc_outliers.txt"
common=(
    --exclude-list "$exclude_list"
    --sensitivity-label qc-outliers
    "$@"
)

if [[ "$analysis_set" == "primary" || "$analysis_set" == "all" ]]; then
    bash "${scriptdir}/run_randomise.sh" primary "${common[@]}"
fi
if [[ "$analysis_set" == "secondary" || "$analysis_set" == "all" ]]; then
    bash "${scriptdir}/run_randomise.sh" secondary "${common[@]}"
fi
if [[ "$analysis_set" == "smith09" || "$analysis_set" == "all" ]]; then
    bash "${scriptdir}/run_randomise.sh" smith09 "${common[@]}"
fi
if [[ "$analysis_set" == "smith09-secondary" || "$analysis_set" == "all" ]]; then
    bash "${scriptdir}/run_randomise.sh" smith09-secondary "${common[@]}"
fi
