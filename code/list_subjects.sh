#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat <<'USAGE'
Usage: code/list_subjects.sh [--output PATH] [--force]

Write task-rest BIDS participant labels to code/sublist.txt in deterministic order.
Set BIDS_DIR to override /ZPOOL/data/projects/r21-cardgame/bids.
USAGE
}

scriptdir="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
bidsdir="${BIDS_DIR:-/ZPOOL/data/projects/r21-cardgame/bids}"
task="${TASK_ID:-rest}"
output="${scriptdir}/sublist.txt"
force=0

while (($#)); do
    case "$1" in
        --output) output="${2:-}"; shift 2 ;;
        --force) force=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *) echo "ERROR: Unknown argument: $1" >&2; usage >&2; exit 1 ;;
    esac
done

[[ -d "$bidsdir" ]] || { echo "ERROR: BIDS directory not found: $bidsdir" >&2; exit 1; }
if [[ -e "$output" && "$force" -ne 1 ]]; then
    echo "ERROR: Output already exists: $output (use --force to replace it)" >&2
    exit 1
fi

mkdir -p "$(dirname "$output")"
shopt -s nullglob
participants=("$bidsdir"/sub-*)
subjects=()
for participant in "${participants[@]}"; do
    [[ -d "$participant" ]] || continue
    sub="$(basename "$participant")"
    bold_jsons=("$participant"/func/"${sub}_task-${task}_"*_bold.json)
    ((${#bold_jsons[@]})) && subjects+=("$sub")
done
if ((${#subjects[@]} == 0)); then
    echo "ERROR: No task-${task} participants found in: $bidsdir" >&2
    exit 1
fi

printf '%s\n' "${subjects[@]}" | LC_ALL=C sort -u > "$output"

printf 'Wrote %s participants to %s\n' "$(wc -l < "$output" | tr -d ' ')" "$output"
