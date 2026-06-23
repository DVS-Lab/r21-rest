#!/usr/bin/env bash
set -euo pipefail

# Run the predefined participant-level QC exclusion sensitivity analysis.

usage() {
    cat <<'USAGE'
Usage: code/run_randomise_qc_sensitivity.sh {primary|smith09|all} [run_randomise options]

Exclude participants listed in code/exclude_qc_outliers.txt and write all
contrast inputs and randomise outputs under sensitivity-qc-outliers folders.

  primary  Data-derived primary ICA networks (49 jobs)
  smith09  Direct Smith09 primary maps (28 jobs)
  all      Run primary followed by Smith09 (77 jobs)
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
    primary|smith09|all) ;;
    *) echo "ERROR: Analysis set must be primary, smith09, or all." >&2; usage >&2; exit 1 ;;
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
if [[ "$analysis_set" == "smith09" || "$analysis_set" == "all" ]]; then
    bash "${scriptdir}/run_randomise.sh" smith09 "${common[@]}"
fi
