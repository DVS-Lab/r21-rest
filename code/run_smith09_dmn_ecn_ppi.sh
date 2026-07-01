#!/usr/bin/env bash
set -euo pipefail

# Add a DMN x ECN timecourse to Smith09 stage 2 without editing dual_regression.

usage() {
    cat <<'USAGE'
Usage: code/run_smith09_dmn_ecn_ppi.sh [options]

Reuse the completed Smith09 denoised dual-regression stage-1 timecourses,
append a centered DMN x ECN interaction column, and rerun stage 2. The output
is a dual-regression-like directory with 11 maps per input run. Component 11 is
the physio-physio interaction map and can be passed to
make_dual_regression_contrasts.sh.

Options:
  --max-jobs N          Concurrent fsl_glm jobs (default: 24)
  --overwrite           Remove an existing output directory first
  --dry-run             Print resolved paths and exit

Environment overrides:
  FSL_OUTPUT_DIR        Project FSL derivatives directory
  SOURCE_DR_DIR        Existing Smith09 denoised dual-regression directory
  OUTPUT_DR_DIR        Output directory for the 11-column stage-2 run
USAGE
}

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

scriptdir="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
maindir="$(dirname "$scriptdir")"
derivdir="${DERIVATIVES_ROOT:-${maindir}/derivatives}"
fsldir="${FSL_OUTPUT_DIR:-${derivdir}/fsl}"
source_dr="${SOURCE_DR_DIR:-${fsldir}/dual-regression_smith09_denoised.dr}"
output_dr="${OUTPUT_DR_DIR:-${fsldir}/dual-regression_smith09_denoised_ppi-dmn-ecn.dr}"
mapping="${source_dr}/input_order.tsv"
mask="${source_dr}/mask.nii.gz"

printf 'Source dual regression: %s\n' "$source_dr" >&2
printf 'Output dual regression: %s\n' "$output_dr" >&2
printf 'Input order: %s\n' "$mapping" >&2
printf 'Mask: %s\n' "$mask" >&2
printf 'Interaction: Smith09 component 4 (DMN) x component 8 (ECN); output component 11\n' >&2
printf 'Concurrent fsl_glm jobs: %s\n' "$maxjobs" >&2

if ((dryrun)); then
    exit 0
fi

command -v fsl_glm >/dev/null 2>&1 || { echo "ERROR: fsl_glm is not on PATH." >&2; exit 1; }
command -v fslnvols >/dev/null 2>&1 || { echo "ERROR: fslnvols is not on PATH." >&2; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "ERROR: python3 is not on PATH." >&2; exit 1; }
[[ -f "$mapping" ]] || { echo "ERROR: input_order.tsv not found: $mapping" >&2; exit 1; }
[[ -f "$mask" ]] || { echo "ERROR: mask not found: $mask" >&2; exit 1; }
if [[ -e "$output_dr" ]]; then
    if ((overwrite)); then
        rm -rf "$output_dr"
    else
        echo "ERROR: Output already exists: $output_dr" >&2
        exit 1
    fi
fi

mkdir -p "$output_dr/designs" "$output_dr/logs"
cp "$mapping" "${output_dr}/input_order.tsv"
cp "$mask" "${output_dr}/mask.nii.gz"
cat >"${output_dr}/network_labels.tsv" <<'EOF'
component	network	source
1	primary-visual	Smith09
2	occipital-pole	Smith09
3	lateral-visual	Smith09
4	dmn	Smith09
5	cerebellum	Smith09
6	sensorimotor	Smith09
7	auditory	Smith09
8	ecn	Smith09
9	right-fpn	Smith09
10	left-fpn	Smith09
11	dmn-x-ecn	centered product of Smith09 stage-1 DMN and ECN timecourses
EOF

build_design() {
    local label="$1"
    local stage1="${source_dr}/dr_stage1_${label}.txt"
    local design="${output_dr}/designs/dr_stage1_${label}_ppi-dmn-ecn.txt"
    [[ -f "$stage1" ]] || { echo "ERROR: Stage-1 timecourse not found: $stage1" >&2; return 1; }
    python3 - "$stage1" "$design" <<'PY'
from pathlib import Path
import sys
import numpy as np

source = Path(sys.argv[1])
target = Path(sys.argv[2])
matrix = np.loadtxt(source, dtype=float)
if matrix.ndim != 2:
    raise SystemExit(f"ERROR: stage-1 matrix is not 2D: {source}")
if matrix.shape[1] != 10 and matrix.shape[0] == 10:
    matrix = matrix.T
if matrix.shape[1] != 10:
    raise SystemExit(f"ERROR: expected 10 Smith09 columns, got {matrix.shape}: {source}")

dmn = matrix[:, 3]
ecn = matrix[:, 7]
dmn_z = (dmn - dmn.mean()) / dmn.std(ddof=0)
ecn_z = (ecn - ecn.mean()) / ecn.std(ddof=0)
interaction = dmn_z * ecn_z
interaction = interaction - interaction.mean()
augmented = np.column_stack([matrix, interaction])
np.savetxt(target, augmented, fmt="%.10g", delimiter="\t")
PY
}

run_stage2() {
    local label="$1"
    local input="$2"
    local design="${output_dr}/designs/dr_stage1_${label}_ppi-dmn-ecn.txt"
    local output="${output_dr}/dr_stage2_${label}"
    local zoutput="${output_dr}/dr_stage2_${label}_Z"
    local log="${output_dr}/logs/${label}.log"
    {
        printf 'Label: %s\nInput: %s\nDesign: %s\nOutput: %s\n' "$label" "$input" "$design" "$output"
        fsl_glm \
            -i "$input" \
            -d "$design" \
            -o "$output" \
            --out_z="$zoutput" \
            --demean \
            -m "${output_dr}/mask.nii.gz" \
            --des_norm
        volumes="$(fslnvols "${output}.nii.gz")"
        [[ "$volumes" == "11" ]] || {
            echo "ERROR: Expected 11 stage-2 maps, found $volumes" >&2
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
    build_design "$label"
    (
        run_stage2 "$label" "$file"
    ) || exit 1 &
    running=$((running + 1))
    if ((running >= maxjobs)); then
        if ! wait -n; then failures=$((failures + 1)); fi
        running=$((running - 1))
    fi
done <"$mapping"

while ((running > 0)); do
    if ! wait -n; then failures=$((failures + 1)); fi
    running=$((running - 1))
done

if ((failures > 0)); then
    echo "ERROR: One or more PPI stage-2 jobs failed. Check ${output_dr}/logs" >&2
    exit 1
fi

touch "${output_dr}/.complete"
cat >"${output_dr}/README.md" <<EOF
# Smith09 DMN x ECN Interaction Stage 2

Generated by \`code/run_smith09_dmn_ecn_ppi.sh\`.

This directory reuses \`${source_dr}/dr_stage1_subjectNNNNN.txt\` and appends
an eleventh run-level regressor: the centered product of z-scored Smith09 DMN
(component 4) and ECN (component 8) stage-1 timecourses. The original ten
Smith09 timecourses are retained as columns 1-10. Stage 2 is rerun with
\`fsl_glm --demean --des_norm\`, matching the original dual-regression stage-2
normalization. Component 11 is therefore the DMN-by-ECN physio-physio
interaction map.
EOF

cat >&2 <<EOF
Wrote ${output_dr}

Next:
DUAL_REGRESSION_DIR=${output_dr} code/make_dual_regression_contrasts.sh smith09 11 \\
  --output-dir ${output_dr}/contrasts/component-0011_stat-beta
${output_dr}/contrasts/component-0011_stat-beta/run_randomise.sh
EOF
