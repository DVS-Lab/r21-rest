#!/usr/bin/env bash
set -euo pipefail

# Add standardized DMN interaction timecourses to the 11-map stage-2 model.

usage() {
    cat <<'USAGE'
Usage: code/run_smith09_ppi.sh [all|dmn-ecn|dmn-reward|dmn-left-fpn|dmn-right-fpn] [options]

Reuse the completed 11-map Smith09-plus-reward stage-1 timecourses. For each
requested analysis, z-score all 11 columns within run, append a z-scored DMN
interaction, and rerun stage 2. Components 1-11 retain their recorded labels;
component 12 is the interaction.

Options:
  --max-jobs N  Concurrent fsl_glm jobs across all PPI analyses (default: 24)
  --overwrite   Replace existing selected output directories
  --dry-run     Print resolved paths and exit

Environment overrides:
  FSL_OUTPUT_DIR  Project FSL derivatives directory
  SOURCE_DR_DIR   Completed 11-map dual-regression directory
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

maxjobs="${MAX_JOBS:-24}"
overwrite=0
dryrun=0
while (($#)); do
    case "$1" in
        --max-jobs) maxjobs="${2:-}"; shift 2 ;;
        --overwrite) overwrite=1; shift ;;
        --dry-run|--render-only) dryrun=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *) echo "ERROR: Unknown argument: $1" >&2; usage >&2; exit 1 ;;
    esac
done
[[ "$maxjobs" =~ ^[1-9][0-9]*$ ]] || { echo "ERROR: --max-jobs must be positive." >&2; exit 1; }

if [[ "$ppi_set" == "all" ]]; then
    ppis=(dmn-ecn dmn-reward dmn-left-fpn dmn-right-fpn)
else
    ppis=("$ppi_set")
fi

partner_component() {
    case "$1" in
        dmn-ecn) echo 8 ;;
        dmn-right-fpn) echo 9 ;;
        dmn-left-fpn) echo 10 ;;
        dmn-reward) echo 11 ;;
    esac
}

partner_network() {
    case "$1" in
        dmn-ecn) echo ecn ;;
        dmn-right-fpn) echo right-fpn ;;
        dmn-left-fpn) echo left-fpn ;;
        dmn-reward) echo brain-reward-signature ;;
    esac
}

scriptdir="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
maindir="$(dirname "$scriptdir")"
derivdir="${DERIVATIVES_ROOT:-${maindir}/derivatives}"
fsldir="${FSL_OUTPUT_DIR:-${derivdir}/fsl}"
source_dr="${SOURCE_DR_DIR:-${fsldir}/dual-regression_smith09-reward_denoised.dr}"
mapping="${source_dr}/input_order.tsv"
mask="${source_dr}/mask.nii.gz"
source_labels="${source_dr}/network_labels.tsv"

printf 'Source dual regression: %s\n' "$source_dr" >&2
printf 'PPI analyses: %s\n' "${ppis[*]}" >&2
printf 'Source columns: 11; output columns: 12; timecourse scaling: within-run z-score\n' >&2
printf 'Concurrent fsl_glm jobs: %s\n' "$maxjobs" >&2
for ppi in "${ppis[@]}"; do
    output_dr="${fsldir}/dual-regression_smith09-reward_denoised_ppi-${ppi}.dr"
    printf '  %s: DMN (4) x %s (%s) -> component 12\n' \
        "$output_dr" "$(partner_network "$ppi")" "$(partner_component "$ppi")" >&2
done

if ((dryrun)); then
    exit 0
fi

for command in fsl_glm fslnvols python3; do
    command -v "$command" >/dev/null 2>&1 || { echo "ERROR: $command is not on PATH." >&2; exit 1; }
done
[[ -f "$mapping" ]] || { echo "ERROR: input_order.tsv not found: $mapping" >&2; exit 1; }
[[ -f "$mask" ]] || { echo "ERROR: mask not found: $mask" >&2; exit 1; }
[[ -f "$source_labels" ]] || { echo "ERROR: network_labels.tsv not found: $source_labels" >&2; exit 1; }

active_ppis=()
for ppi in "${ppis[@]}"; do
    output_dr="${fsldir}/dual-regression_smith09-reward_denoised_ppi-${ppi}.dr"
    if [[ -e "$output_dr" ]]; then
        if ((overwrite)); then
            rm -rf "$output_dr"
        elif [[ -f "${output_dr}/.complete" ]]; then
            echo "Already complete: $output_dr" >&2
            continue
        else
            echo "ERROR: Incomplete output already exists: $output_dr" >&2
            echo "Use --overwrite only after reviewing that directory." >&2
            exit 1
        fi
    fi
    mkdir -p "$output_dr/designs" "$output_dr/logs"
    cp "$mapping" "${output_dr}/input_order.tsv"
    cp "$mask" "${output_dr}/mask.nii.gz"
    cp "$source_labels" "${output_dr}/network_labels.tsv"
    printf '12\tdmn-x-%s\twithin-run z-scored product of components 4 and %s\n' \
        "$(partner_network "$ppi")" "$(partner_component "$ppi")" >>"${output_dr}/network_labels.tsv"
    active_ppis+=("$ppi")
done

((${#active_ppis[@]} > 0)) || { echo "All requested PPI analyses are already complete." >&2; exit 0; }

build_design() {
    local ppi="$1"
    local label="$2"
    local output_dr="${fsldir}/dual-regression_smith09-reward_denoised_ppi-${ppi}.dr"
    local source="${source_dr}/dr_stage1_${label}.txt"
    local design="${output_dr}/designs/dr_stage1_${label}_ppi-${ppi}.txt"
    local partner
    partner="$(partner_component "$ppi")"
    [[ -f "$source" ]] || { echo "ERROR: Stage-1 timecourse not found: $source" >&2; return 1; }
    python3 - "$source" "$design" "$partner" <<'PY'
from pathlib import Path
import sys
import numpy as np

source = Path(sys.argv[1])
target = Path(sys.argv[2])
partner = int(sys.argv[3]) - 1
matrix = np.loadtxt(source, dtype=float)
if matrix.ndim != 2:
    raise SystemExit(f"ERROR: stage-1 matrix is not 2D: {source}")
if matrix.shape[1] != 11 and matrix.shape[0] == 11:
    matrix = matrix.T
if matrix.shape[1] != 11:
    raise SystemExit(f"ERROR: expected 11 source columns, got {matrix.shape}: {source}")
if not np.isfinite(matrix).all():
    raise SystemExit(f"ERROR: non-finite stage-1 value: {source}")

standard_deviations = matrix.std(axis=0, ddof=0)
if np.any(standard_deviations <= 0):
    columns = (np.flatnonzero(standard_deviations <= 0) + 1).tolist()
    raise SystemExit(f"ERROR: constant stage-1 column(s) {columns}: {source}")
standardized = (matrix - matrix.mean(axis=0)) / standard_deviations
interaction = standardized[:, 3] * standardized[:, partner]
interaction_std = interaction.std(ddof=0)
if not np.isfinite(interaction_std) or interaction_std <= 0:
    raise SystemExit(f"ERROR: constant/non-finite interaction: {source}")
interaction = (interaction - interaction.mean()) / interaction_std
np.savetxt(target, np.column_stack([standardized, interaction]), fmt="%.10g", delimiter="\t")
PY
}

run_stage2() {
    local ppi="$1"
    local label="$2"
    local input="$3"
    local output_dr="${fsldir}/dual-regression_smith09-reward_denoised_ppi-${ppi}.dr"
    local design="${output_dr}/designs/dr_stage1_${label}_ppi-${ppi}.txt"
    local output="${output_dr}/dr_stage2_${label}"
    local zoutput="${output_dr}/dr_stage2_${label}_Z"
    local log="${output_dr}/logs/${label}.log"
    {
        printf 'PPI: %s\nLabel: %s\nInput: %s\nDesign: %s\nOutput: %s\n' \
            "$ppi" "$label" "$input" "$design" "$output"
        fsl_glm \
            -i "$input" \
            -d "$design" \
            -o "$output" \
            --out_z="$zoutput" \
            --demean \
            -m "${output_dr}/mask.nii.gz" \
            --des_norm
        volumes="$(fslnvols "${output}.nii.gz")"
        [[ "$volumes" == "12" ]] || {
            echo "ERROR: Expected 12 stage-2 maps, found $volumes" >&2
            exit 1
        }
    } >"$log" 2>&1
}

failures=0
running=0
while IFS=$'\t' read -r index label participant run condition order file; do
    [[ "$index" == "dual_regression_index" ]] && continue
    [[ -n "$label" ]] || continue
    [[ -f "$file" ]] || { echo "ERROR: Input BOLD not found for $label: $file" >&2; exit 1; }
    for ppi in "${active_ppis[@]}"; do
        build_design "$ppi" "$label"
        (run_stage2 "$ppi" "$label" "$file") &
        running=$((running + 1))
        if ((running >= maxjobs)); then
            if ! wait -n; then failures=$((failures + 1)); fi
            running=$((running - 1))
        fi
    done
done <"$mapping"

while ((running > 0)); do
    if ! wait -n; then failures=$((failures + 1)); fi
    running=$((running - 1))
done

if ((failures > 0)); then
    echo "ERROR: One or more PPI stage-2 jobs failed. Check the PPI logs directories." >&2
    exit 1
fi

for ppi in "${active_ppis[@]}"; do
    output_dr="${fsldir}/dual-regression_smith09-reward_denoised_ppi-${ppi}.dr"
    touch "${output_dr}/.complete"
    cat >"${output_dr}/README.md" <<EOF
# Smith09 Plus Reward ${ppi} Interaction

Components 1-11 come from the Smith09-plus-reward stage-1 model. Component 12
is the within-run z-scored product for ${ppi}. Stage 2 used
\`fsl_glm --demean --des_norm\`.
EOF
    echo "Complete: $output_dr" >&2
done
