#!/usr/bin/env bash
set -euo pipefail

# Match all four group-ICA analyses to Smith09 and combine the results.

usage() {
    cat <<'USAGE'
Usage: code/run_match_smith09.sh [--dry-run]

Run Smith09 matching for smoothed and denoised data at automatic and fixed-20
dimensionality, then write one four-analysis comparison table.
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

for data_set in smoothed denoised; do
    for dimension in 0 20; do
        args=("$data_set" "$dimension")
        ((dryrun)) && args+=(--dry-run)
        bash "${scriptdir}/match_smith09.sh" "${args[@]}"
    done
done

if ((dryrun)); then
    echo "Summary: python3 code/summarize_smith09_analyses.py" >&2
    exit 0
fi

python3 "${scriptdir}/summarize_smith09_analyses.py"
