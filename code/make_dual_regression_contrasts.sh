#!/usr/bin/env bash
set -euo pipefail

# Build paired condition differences for one dual-regression component.

usage() {
    cat <<'USAGE'
Usage: code/make_dual_regression_contrasts.sh {smith09|0|20} COMPONENT [options]

Create all seven within-participant condition contrasts for one 1-based
dual-regression component, merge each contrast across participants, and write
one-sample FSL design files plus a run_randomise.sh launcher.

Options:
  --map-type {beta|z}  Stage-2 map type (default: beta)
  --output-dir PATH    Override the component contrast output directory
  --dry-run            Print resolved paths and planned operations only

The primary analysis should use beta: dr_stage2_subjectNNNNN.nii.gz. The z
option uses dr_stage2_subjectNNNNN_Z.nii.gz as an explicit sensitivity check.
USAGE
}

analysis="${1:-}"
component="${2:-}"
if [[ -z "$analysis" || "$analysis" == "--help" || "$analysis" == "-h" ]]; then
    usage
    [[ "$analysis" == "--help" || "$analysis" == "-h" ]] && exit 0
    exit 1
fi
[[ "$component" =~ ^[1-9][0-9]*$ ]] || {
    echo "ERROR: COMPONENT must be a positive 1-based integer." >&2
    usage >&2
    exit 1
}
shift 2

case "$analysis" in
    smith09) analysis_label="smith09_denoised" ;;
    0) analysis_label="denoised_dim-00_task-rest" ;;
    20) analysis_label="denoised_dim-20_task-rest" ;;
    *) echo "ERROR: Analysis must be smith09, 0, or 20." >&2; usage >&2; exit 1 ;;
esac

map_type="beta"
outputdir=""
dryrun=0
while (($#)); do
    case "$1" in
        --map-type) map_type="${2:-}"; shift 2 ;;
        --output-dir) outputdir="${2:-}"; shift 2 ;;
        --dry-run|--render-only) dryrun=1; shift ;;
        --help|-h) usage; exit 0 ;;
        *) echo "ERROR: Unknown argument: $1" >&2; usage >&2; exit 1 ;;
    esac
done

case "$map_type" in
    beta) stage2_suffix="" ;;
    z) stage2_suffix="_Z" ;;
    *) echo "ERROR: --map-type must be beta or z." >&2; exit 1 ;;
esac

scriptdir="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
maindir="$(dirname "$scriptdir")"
derivdir="${DERIVATIVES_ROOT:-${maindir}/derivatives}"
fsldir="${FSL_OUTPUT_DIR:-${derivdir}/fsl}"
task="${TASK_ID:-rest}"
drdir="${DUAL_REGRESSION_DIR:-${fsldir}/dual-regression_${analysis_label}.dr}"
mapping="${DUAL_REGRESSION_INPUT_ORDER:-${drdir}/input_order.tsv}"
mask="${DUAL_REGRESSION_MASK:-${drdir}/mask.nii.gz}"
component_padded="$(printf '%04d' "$component")"
component_index=$((component - 1))
outputdir="${outputdir:-${drdir}/contrasts/component-${component_padded}_stat-${map_type}}"
scratchroot="${WORK_ROOT:-/ZPOOL/data/scratch/${USER:-$(whoami)}}"

contrasts=(
    both-minus-sham
    both-minus-rtpj
    both-minus-vlpfc
    rtpj-minus-vlpfc
    rtpj-minus-sham
    vlpfc-minus-sham
    both-minus-mean-rtpj-vlpfc
)

printf 'Analysis: %s\n' "$analysis" >&2
printf 'Dual regression: %s\n' "$drdir" >&2
printf 'Input order: %s\n' "$mapping" >&2
printf 'Component: %d (FSL volume %d)\n' "$component" "$component_index" >&2
printf 'Stage-2 map type: %s (dr_stage2_subjectNNNNN%s.nii.gz)\n' \
    "$map_type" "$stage2_suffix" >&2
printf 'Output: %s\n' "$outputdir" >&2
printf 'Contrasts: %s\n' "${contrasts[*]}" >&2
printf 'Operations: fslroi, fslmaths subtraction, fslmerge, one-sample FSL designs\n' >&2

if [[ "$map_type" == "z" ]]; then
    echo "WARNING: Z maps are a sensitivity analysis; beta maps are primary." >&2
fi
if ((dryrun)); then
    exit 0
fi

for command in fslroi fslmaths fslmerge fslnvols; do
    command -v "$command" >/dev/null 2>&1 || {
        echo "ERROR: $command is not on PATH." >&2
        exit 1
    }
done
[[ -f "$mapping" ]] || { echo "ERROR: Input-order table not found: $mapping" >&2; exit 1; }
[[ -f "$mask" ]] || { echo "ERROR: Dual-regression mask not found: $mask" >&2; exit 1; }
[[ ! -e "$outputdir" ]] || { echo "ERROR: Output already exists: $outputdir" >&2; exit 1; }

mkdir -p "${scratchroot}/r21-rest"
workdir="$(mktemp -d "${scratchroot}/r21-rest/dr_contrasts.XXXXXX")"
cleanup() {
    rm -rf "$workdir"
}
trap cleanup EXIT

plan="${workdir}/participant_stage2.tsv"
if ! awk -F $'\t' '
    NR == 1 {
        for (column = 1; column <= NF; column++) column_index[$column] = column
        if (!("dual_regression_label" in column_index) || !("participant" in column_index) || !("condition" in column_index)) {
            print "ERROR: input_order.tsv is missing required columns." > "/dev/stderr"
            exit 1
        }
        print "participant\tsham\trtpj\tvlpfc\tboth"
        next
    }
    NF {
        participant = $column_index["participant"]
        label = $column_index["dual_regression_label"]
        condition = tolower($column_index["condition"])
        if (participant == "" || participant == "unknown") {
            print "ERROR: Missing participant label in input_order.tsv." > "/dev/stderr"
            bad = 1
            next
        }
        if (condition != "sham" && condition != "rtpj" && condition != "vlpfc" && condition != "both") {
            print "ERROR: Unexpected condition for " participant ": " condition > "/dev/stderr"
            bad = 1
            next
        }
        key = participant SUBSEP condition
        if (key in labels) {
            print "ERROR: Duplicate " condition " run for " participant "." > "/dev/stderr"
            bad = 1
            next
        }
        labels[key] = label
        if (!(participant in subject_seen)) {
            subject_seen[participant] = 1
            subjects[++subject_count] = participant
        }
    }
    END {
        for (subject_number = 1; subject_number <= subject_count; subject_number++) {
            participant = subjects[subject_number]
            missing = ""
            if (!((participant SUBSEP "sham") in labels)) missing = missing " sham"
            if (!((participant SUBSEP "rtpj") in labels)) missing = missing " rtpj"
            if (!((participant SUBSEP "vlpfc") in labels)) missing = missing " vlpfc"
            if (!((participant SUBSEP "both") in labels)) missing = missing " both"
            if (missing != "") {
                print "ERROR: " participant " is missing condition(s):" missing > "/dev/stderr"
                bad = 1
            } else {
                print participant "\t" labels[participant SUBSEP "sham"] "\t" \
                    labels[participant SUBSEP "rtpj"] "\t" \
                    labels[participant SUBSEP "vlpfc"] "\t" \
                    labels[participant SUBSEP "both"]
            }
        }
        if (bad || subject_count == 0) exit 1
    }
' "$mapping" >"$plan"; then
    exit 1
fi

participant_count=$(($(wc -l <"$plan") - 1))
((participant_count > 0)) || { echo "ERROR: No complete participants found." >&2; exit 1; }

while IFS=$'\t' read -r participant sham_label rtpj_label vlpfc_label both_label; do
    [[ "$participant" == "participant" ]] && continue
    for label in "$sham_label" "$rtpj_label" "$vlpfc_label" "$both_label"; do
        source="${drdir}/dr_stage2_${label}${stage2_suffix}.nii.gz"
        [[ -f "$source" ]] || { echo "ERROR: Stage-2 image not found: $source" >&2; exit 1; }
        volumes="$(fslnvols "$source")"
        [[ "$volumes" =~ ^[1-9][0-9]*$ ]] || {
            echo "ERROR: Could not read the volume count: $source" >&2
            exit 1
        }
        ((component <= volumes)) || {
            echo "ERROR: Component $component exceeds $volumes maps in $source" >&2
            exit 1
        }
    done
done <"$plan"

mkdir -p "$outputdir"
for contrast in "${contrasts[@]}"; do
    mkdir -p "${outputdir}/${contrast}"
done

subject_order="${outputdir}/subject_order.tsv"
printf 'randomise_index\tparticipant\n' >"$subject_order"
randomise_index=0
while IFS=$'\t' read -r participant sham_label rtpj_label vlpfc_label both_label; do
    [[ "$participant" == "participant" ]] && continue
    printf '%d\t%s\n' "$randomise_index" "$participant" >>"$subject_order"
    randomise_index=$((randomise_index + 1))

    participant_work="${workdir}/${participant}"
    mkdir -p "$participant_work"
    sham="${participant_work}/sham.nii.gz"
    rtpj="${participant_work}/rtpj.nii.gz"
    vlpfc="${participant_work}/vlpfc.nii.gz"
    both="${participant_work}/both.nii.gz"
    fslroi "${drdir}/dr_stage2_${sham_label}${stage2_suffix}.nii.gz" "$sham" "$component_index" 1
    fslroi "${drdir}/dr_stage2_${rtpj_label}${stage2_suffix}.nii.gz" "$rtpj" "$component_index" 1
    fslroi "${drdir}/dr_stage2_${vlpfc_label}${stage2_suffix}.nii.gz" "$vlpfc" "$component_index" 1
    fslroi "${drdir}/dr_stage2_${both_label}${stage2_suffix}.nii.gz" "$both" "$component_index" 1

    stem="${participant}_task-${task}_component-${component_padded}_stat-${map_type}"
    fslmaths "$both" -sub "$sham" \
        "${outputdir}/both-minus-sham/${stem}_contrast-both-minus-sham.nii.gz" -odt float
    fslmaths "$both" -sub "$rtpj" \
        "${outputdir}/both-minus-rtpj/${stem}_contrast-both-minus-rtpj.nii.gz" -odt float
    fslmaths "$both" -sub "$vlpfc" \
        "${outputdir}/both-minus-vlpfc/${stem}_contrast-both-minus-vlpfc.nii.gz" -odt float
    fslmaths "$rtpj" -sub "$vlpfc" \
        "${outputdir}/rtpj-minus-vlpfc/${stem}_contrast-rtpj-minus-vlpfc.nii.gz" -odt float
    fslmaths "$rtpj" -sub "$sham" \
        "${outputdir}/rtpj-minus-sham/${stem}_contrast-rtpj-minus-sham.nii.gz" -odt float
    fslmaths "$vlpfc" -sub "$sham" \
        "${outputdir}/vlpfc-minus-sham/${stem}_contrast-vlpfc-minus-sham.nii.gz" -odt float
    fslmaths "$both" -mul 2 -sub "$rtpj" -sub "$vlpfc" -div 2 \
        "${outputdir}/both-minus-mean-rtpj-vlpfc/${stem}_contrast-both-minus-mean-rtpj-vlpfc.nii.gz" -odt float
done <"$plan"

for contrast in "${contrasts[@]}"; do
    images=()
    while IFS=$'\t' read -r participant _sham _rtpj _vlpfc _both; do
        [[ "$participant" == "participant" ]] && continue
        images+=(
            "${outputdir}/${contrast}/${participant}_task-${task}_component-${component_padded}_stat-${map_type}_contrast-${contrast}.nii.gz"
        )
    done <"$plan"
    group_input="${outputdir}/${contrast}/group_task-${task}_component-${component_padded}_stat-${map_type}_contrast-${contrast}.nii.gz"
    fslmerge -t "$group_input" "${images[@]}"
done

design_mat="${outputdir}/design.mat"
{
    printf '/NumWaves\t1\n'
    printf '/NumPoints\t%d\n' "$participant_count"
    printf '/PPheights\t1\n\n'
    printf '/Matrix\n'
    for ((_index = 0; _index < participant_count; _index++)); do printf '1\n'; done
} >"$design_mat"

design_con="${outputdir}/design.con"
cat >"$design_con" <<'EOF'
/ContrastName1	Positive
/ContrastName2	Negative
/NumWaves	1
/NumContrasts	2
/PPheights	1	1
/RequiredEffect	1	1

/Matrix
1
-1
EOF

design_grp="${outputdir}/design.grp"
{
    printf '/NumWaves\t1\n'
    printf '/NumPoints\t%d\n\n' "$participant_count"
    printf '/Matrix\n'
    for ((_index = 0; _index < participant_count; _index++)); do printf '1\n'; done
} >"$design_grp"

randomise_script="${outputdir}/run_randomise.sh"
{
    cat <<'EOF'
#!/usr/bin/env bash
set -euo pipefail

nperm="${N_PERM:-5000}"
EOF
    printf 'mkdir -p %q\n' "${outputdir}/randomise"
    for contrast in "${contrasts[@]}"; do
        group_input="${outputdir}/${contrast}/group_task-${task}_component-${component_padded}_stat-${map_type}_contrast-${contrast}.nii.gz"
        randomise_prefix="${outputdir}/randomise/task-${task}_component-${component_padded}_stat-${map_type}_contrast-${contrast}"
        printf 'randomise -i %q -o %q -m %q -d %q -t %q -e %q -n "$nperm" -T\n' \
            "$group_input" "$randomise_prefix" "$mask" "$design_mat" "$design_con" "$design_grp"
    done
} >"$randomise_script"
chmod +x "$randomise_script"

echo "Participants: $participant_count" >&2
echo "Wrote $subject_order" >&2
echo "Wrote merged contrast inputs under $outputdir" >&2
echo "Next: $randomise_script" >&2
