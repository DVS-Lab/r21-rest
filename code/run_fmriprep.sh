#!/usr/bin/env bash
set -euo pipefail

# Run fMRIPrep for a list of participants.
#
# Usage:
#   bash code/run_fmriprep.sh
#   bash code/run_fmriprep.sh --sublist code/sublist.txt --pilot-one
#   bash code/run_fmriprep.sh --dry-run

usage() {
    cat <<'USAGE'
Usage: code/run_fmriprep.sh [--sublist PATH] [--max-jobs N] [--pilot-one] [--rerun-complete] [--dry-run]

Run fMRIPrep for participants listed one per line. Blank lines and # comments
are ignored. If --sublist is not provided, the script uses code/sublist.txt,
falling back to subjects.txt in the project root if it exists.
Participants with complete fMRIPrep outputs are skipped by default.
USAGE
}

scriptdir="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
maindir="$(dirname "$scriptdir")"

sublist=""
maxjobs="${FMRIPREP_MAX_JOBS:-4}"
pilot_one=0
rerun_complete=0
dryrun=0

while (($#)); do
    case "$1" in
        --sublist|--subjects) sublist="${2:-}"; shift 2 ;;
        --max-jobs) maxjobs="${2:-}"; shift 2 ;;
        --pilot-one) pilot_one=1; shift ;;
        --rerun-complete) rerun_complete=1; shift ;;
        --dry-run|--render-only) dryrun=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *) echo "ERROR: Unknown argument: $1" >&2; usage >&2; exit 1 ;;
    esac
done

if [[ -z "$sublist" ]]; then
    if [[ -f "${scriptdir}/sublist.txt" ]]; then
        sublist="${scriptdir}/sublist.txt"
    elif [[ -f "${maindir}/subjects.txt" ]]; then
        sublist="${maindir}/subjects.txt"
    else
        echo "ERROR: No sublist found." >&2
        echo "Create one with: code/list_subjects.sh --output code/sublist.txt" >&2
        exit 1
    fi
fi

[[ -f "$sublist" ]] || { echo "ERROR: Sublist not found: $sublist" >&2; exit 1; }
[[ "$maxjobs" =~ ^[1-9][0-9]*$ ]] || { echo "ERROR: --max-jobs must be a positive integer." >&2; exit 1; }
if (( maxjobs > 5 )); then
    echo "ERROR: Refusing more than 5 concurrent fMRIPrep jobs." >&2
    exit 1
fi
if (( maxjobs == 5 )); then
    echo "WARNING: Running 5 concurrent jobs is an explicit override; verify host resources first." >&2
fi

subjects=()
while IFS= read -r sub; do
    subjects+=("$sub")
done < <(
    while IFS= read -r line || [[ -n "$line" ]]; do
        line="${line%%#*}"
        line="${line#"${line%%[![:space:]]*}"}"
        line="${line%"${line##*[![:space:]]}"}"
        [[ -z "$line" ]] && continue
        line="${line#sub-}"
        printf '%s\n' "$line"
    done < "$sublist" | LC_ALL=C sort -u
)

if ((${#subjects[@]} == 0)); then
    echo "ERROR: No participants found in $sublist" >&2
    exit 1
fi

if (( ! rerun_complete )); then
    bidsdir="${BIDS_DIR:-/ZPOOL/data/projects/r21-cardgame/bids}"
    if [[ -d "$bidsdir" ]]; then
        incomplete_subjects=()
        while IFS= read -r sub; do
            [[ -n "$sub" ]] && incomplete_subjects+=("${sub#sub-}")
        done < <(
            python3 "${scriptdir}/check_preprocessing_status.py" \
                --subjects "$sublist" \
                --print-incomplete-fmriprep
        )
        subjects=("${incomplete_subjects[@]}")
        if ((${#subjects[@]} == 0)); then
            echo "All listed participants have complete fMRIPrep outputs; nothing to run." >&2
            exit 0
        fi
        echo "Participants requiring fMRIPrep: ${#subjects[@]}" >&2
    elif (( dryrun )); then
        echo "WARNING: BIDS directory unavailable; dry run cannot skip complete participants." >&2
    else
        echo "ERROR: BIDS directory not found: $bidsdir" >&2
        exit 1
    fi
fi

if (( pilot_one )); then
    subjects=("${subjects[0]}")
    echo "Pilot mode: ${subjects[0]}" >&2
fi

logdir="${maindir}/derivatives/logs/fmriprep"
if (( ! dryrun )); then
    mkdir -p "$logdir"
fi

script="${scriptdir}/fmriprep.sh"
failures=0
pids=()

for sub in "${subjects[@]}"; do
    while [[ "$(jobs -rp | wc -l | tr -d ' ')" -ge "$maxjobs" ]]; do
        sleep 5
    done

    if (( dryrun )); then
        bash "$script" "$sub" --dry-run
        continue
    fi

    stamp="$(date -u '+%Y%m%dT%H%M%SZ')"
    logfile="${logdir}/sub-${sub}_${stamp}.log"
    echo "Launching sub-${sub}; log: $logfile" >&2
    bash "$script" "$sub" > "$logfile" 2>&1 &
    pids+=("$!")
    sleep 5
done

if (( dryrun )); then
    exit 0
fi

for pid in "${pids[@]}"; do
    if ! wait "$pid"; then
        failures=1
    fi
done

if (( failures )); then
    echo "ERROR: One or more fMRIPrep jobs failed. Check logs in $logdir" >&2
    exit 1
fi

echo "All fMRIPrep jobs completed successfully." >&2
