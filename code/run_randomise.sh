#!/usr/bin/env bash
set -euo pipefail

# Prepare selected components and run their condition contrasts in parallel.

usage() {
    cat <<'USAGE'
Usage: code/run_randomise.sh {dmn|primary|smith09} [options]

Prepare selected dual-regression maps and launch all seven condition contrasts.

  dmn      DMN only: 2 components x 7 contrasts = 14 jobs
  primary  DMN, ECN, and left/right FPN; shared components are run once
  smith09  Direct Smith09 maps 4, 8, 9, and 10 x 7 contrasts = 28 jobs

Options:
  --max-jobs N              Concurrent randomise processes (default: 24)
  --map-type {beta|z}       Stage-2 map type (default: beta)
  --n-perm N                Permutations per job (default: 5000)
  --cluster-threshold VALUE Cluster-forming t threshold (default: 3.1)
  --exclude-list PATH       Participant exclusions for a sensitivity analysis
  --sensitivity-label NAME  Output label used with --exclude-list
  --tfce                     Also calculate TFCE inference (default: off)
  --dry-run                  Print the complete launch plan only
USAGE
}

network_set="${1:-}"
if [[ -z "$network_set" || "$network_set" == "--help" || "$network_set" == "-h" ]]; then
    usage
    [[ "$network_set" == "--help" || "$network_set" == "-h" ]] && exit 0
    exit 1
fi
shift
case "$network_set" in
    dmn|primary|smith09) ;;
    *) echo "ERROR: Network set must be dmn, primary, or smith09." >&2; usage >&2; exit 1 ;;
esac

maxjobs="${RANDOMISE_MAX_JOBS:-24}"
map_type="beta"
nperm="${N_PERM:-5000}"
cluster_threshold="${CLUSTER_THRESHOLD:-3.1}"
exclude_list=""
sensitivity_label=""
tfce=0
dryrun=0
while (($#)); do
    case "$1" in
        --max-jobs) maxjobs="${2:-}"; shift 2 ;;
        --map-type) map_type="${2:-}"; shift 2 ;;
        --n-perm) nperm="${2:-}"; shift 2 ;;
        --cluster-threshold) cluster_threshold="${2:-}"; shift 2 ;;
        --exclude-list) exclude_list="${2:-}"; shift 2 ;;
        --sensitivity-label) sensitivity_label="${2:-}"; shift 2 ;;
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
case "$map_type" in beta|z) ;; *) echo "ERROR: --map-type must be beta or z." >&2; exit 1 ;; esac
if [[ -n "$exclude_list" || -n "$sensitivity_label" ]]; then
    [[ -n "$exclude_list" && -n "$sensitivity_label" ]] || {
        echo "ERROR: --exclude-list and --sensitivity-label must be used together." >&2
        exit 1
    }
    [[ "$sensitivity_label" =~ ^[a-z0-9][a-z0-9-]*$ ]] || {
        echo "ERROR: --sensitivity-label must contain lowercase letters, numbers, or hyphens." >&2
        exit 1
    }
    exclude_list="$(cd "$(dirname "$exclude_list")" >/dev/null 2>&1 && pwd)/$(basename "$exclude_list")"
    [[ -f "$exclude_list" ]] || { echo "ERROR: Exclusion list not found: $exclude_list" >&2; exit 1; }
fi

scriptdir="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
maindir="$(dirname "$scriptdir")"
derivdir="${DERIVATIVES_ROOT:-${maindir}/derivatives}"
fsldir="${FSL_OUTPUT_DIR:-${derivdir}/fsl}"
task="${TASK_ID:-rest}"
comparison="${SMITH09_COMPARISON_TSV:-${fsldir}/diagnostics/smith09_ica_comparison.tsv}"

plan="$(mktemp "${TMPDIR:-/tmp}/r21_randomise_plan.XXXXXX")"
cleanup() {
    rm -f "$plan"
}
trap cleanup EXIT

if [[ "$network_set" == "smith09" ]]; then
    printf 'smith09\tdmn\t4\nsmith09\tecn\t8\nsmith09\tright-fpn\t9\nsmith09\tleft-fpn\t10\n' >"$plan"
elif [[ ! -f "$comparison" ]]; then
    echo "ERROR: Smith09 comparison table not found: $comparison" >&2
    exit 1
elif ! awk -F $'\t' -v network_set="$network_set" '
    NR == 1 {
        for (column = 1; column <= NF; column++) column_index[$column] = column
        required[1] = "data_set"
        required[2] = "dimension"
        required[3] = "network"
        required[4] = "analysis_priority"
        required[5] = "best_component"
        for (item = 1; item <= 5; item++) {
            if (!(required[item] in column_index)) {
                print "ERROR: Missing column in Smith09 comparison table: " required[item] > "/dev/stderr"
                bad = 1
            }
        }
        next
    }
    bad { next }
    $column_index["data_set"] == "denoised" && $column_index["analysis_priority"] == "primary" {
        dimension = $column_index["dimension"]
        network = $column_index["network"]
        component = $column_index["best_component"]
        if (network_set == "dmn" && network != "default_mode") next
        if (dimension == "automatic") analysis = "0"
        else if (dimension == "20") analysis = "20"
        else next

        if (network == "default_mode") label = "dmn"
        else if (network == "executive_control") label = "ecn"
        else if (network == "right_frontoparietal") label = "right-fpn"
        else if (network == "left_frontoparietal") label = "left-fpn"
        else next

        key = analysis SUBSEP component
        if (!(key in plan_index)) {
            plan_index[key] = ++plan_count
            analyses[plan_count] = analysis
            components[plan_count] = component
            labels[plan_count] = label
        } else {
            current = plan_index[key]
            if ((labels[current] == "right-fpn" && label == "left-fpn") || \
                (labels[current] == "left-fpn" && label == "right-fpn")) {
                labels[current] = "bilateral-fpn"
            } else if (labels[current] != label) {
                labels[current] = labels[current] "-" label
            }
        }
    }
    END {
        if (bad) exit 1
        for (item = 1; item <= plan_count; item++) {
            print analyses[item] "\t" labels[item] "\t" components[item]
        }
        if (plan_count == 0) exit 1
    }
' "$comparison" >"$plan"; then
    echo "ERROR: Could not build the primary-network plan." >&2
    exit 1
fi

contrasts=(
    both-minus-sham
    both-minus-rtpj
    both-minus-vlpfc
    rtpj-minus-vlpfc
    rtpj-minus-sham
    vlpfc-minus-sham
    both-minus-mean-rtpj-vlpfc
)
component_count="$(wc -l <"$plan" | tr -d ' ')"
job_count=$((component_count * ${#contrasts[@]}))

printf 'Network set: %s\n' "$network_set" >&2
if [[ "$network_set" == "smith09" ]]; then
    printf 'Component plan: direct Smith09 RSN maps\n' >&2
    printf 'Smith09 maps: %d\n' "$component_count" >&2
else
    printf 'Component plan: %s\n' "$comparison" >&2
    printf 'Unique ICA components: %d\n' "$component_count" >&2
fi
printf 'Randomise jobs: %d; maximum concurrent: %d\n' "$job_count" "$maxjobs" >&2
printf 'Sensitivity label: %s\n' "${sensitivity_label:-none}" >&2
printf 'Exclude list: %s\n' "${exclude_list:-none}" >&2
printf 'Permutations: %d; TFCE: %s; cluster threshold: %s\n' \
    "$nperm" "$([[ "$tfce" == 1 ]] && echo yes || echo no)" "$cluster_threshold" >&2
while IFS=$'\t' read -r analysis network component; do
    printf '  dim=%s network=%s component=%s\n' "$analysis" "$network" "$component" >&2
done <"$plan"

component_path() {
    local analysis="$1"
    local component="$2"
    local analysis_label drdir component_padded
    case "$analysis" in
        smith09) analysis_label="smith09_denoised" ;;
        0) analysis_label="denoised_dim-00_task-rest" ;;
        20) analysis_label="denoised_dim-20_task-rest" ;;
        *) return 1 ;;
    esac
    drdir="${fsldir}/dual-regression_${analysis_label}.dr"
    component_padded="$(printf '%04d' "$component")"
    if [[ -n "$sensitivity_label" ]]; then
        printf '%s\n' "${drdir}/contrasts/sensitivity-${sensitivity_label}/component-${component_padded}_stat-${map_type}"
    else
        printf '%s\n' "${drdir}/contrasts/component-${component_padded}_stat-${map_type}"
    fi
}

component_ready() {
    local analysis="$1"
    local component="$2"
    local component_padded component_dir contrast group_input required
    component_padded="$(printf '%04d' "$component")"
    component_dir="$(component_path "$analysis" "$component")" || return 1
    for required in design.mat design.con design.grp subject_order.tsv; do
        [[ -f "${component_dir}/${required}" ]] || return 1
    done
    for contrast in "${contrasts[@]}"; do
        group_input="${component_dir}/${contrast}/group_task-${task}_component-${component_padded}_stat-${map_type}_contrast-${contrast}.nii.gz"
        [[ -f "$group_input" ]] || return 1
    done
    return 0
}

while IFS=$'\t' read -r analysis _network component; do
    component_dir="$(component_path "$analysis" "$component")"
    if component_ready "$analysis" "$component"; then
        printf 'Contrast inputs already prepared: dim=%s component=%s\n' "$analysis" "$component" >&2
        continue
    fi
    args=("$analysis" "$component" --map-type "$map_type" --output-dir "$component_dir")
    [[ -n "$exclude_list" ]] && args+=(--exclude-list "$exclude_list")
    ((dryrun)) && args+=(--dry-run)
    bash "${scriptdir}/make_dual_regression_contrasts.sh" "${args[@]}"
done <"$plan"

if ((dryrun)); then
    while IFS=$'\t' read -r analysis network component; do
        for contrast in "${contrasts[@]}"; do
            printf 'JOB analysis=%s network=%s component=%s contrast=%s nperm=%s TFCE=%s -c %s\n' \
                "$analysis" "$network" "$component" "$contrast" "$nperm" \
                "$([[ "$tfce" == 1 ]] && echo yes || echo no)" "$cluster_threshold" >&2
        done
    done <"$plan"
    exit 0
fi

logdir="${derivdir}/logs/randomise${sensitivity_label:+/sensitivity-${sensitivity_label}}"
mkdir -p "$logdir"
tfce_args=()
((tfce)) && tfce_args=(--tfce)
pids=()
failures=0
launched=0
while IFS=$'\t' read -r analysis network component; do
    component_dir="$(component_path "$analysis" "$component")"
    for contrast in "${contrasts[@]}"; do
        while [[ "$(jobs -rp | wc -l | tr -d ' ')" -ge "$maxjobs" ]]; do
            sleep 2
        done
        logfile="${logdir}/dim-${analysis}_network-${network}_component-${component}_contrast-${contrast}.log"
        echo "Launching dim-${analysis} ${network} component ${component} ${contrast}; log: $logfile" >&2
        CONTRAST_COMPONENT_DIR="$component_dir" bash "${scriptdir}/randomise.sh" \
            "$analysis" "$network" "$component" "$contrast" \
            --map-type "$map_type" --n-perm "$nperm" \
            --cluster-threshold "$cluster_threshold" \
            "${tfce_args[@]}" >"$logfile" 2>&1 &
        pids+=("$!")
        launched=$((launched + 1))
    done
done <"$plan"

for pid in "${pids[@]}"; do
    if ! wait "$pid"; then
        failures=1
    fi
done
if ((failures)); then
    echo "ERROR: One or more randomise jobs failed. Check $logdir" >&2
    exit 1
fi
echo "Randomise jobs completed successfully: $launched" >&2
