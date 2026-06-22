#!/usr/bin/env bash
set -euo pipefail

# Audit the denoised 4D inputs before group MELODIC.

usage() {
    cat <<'USAGE'
Usage: code/check_melodic_inputs.sh [--input-list PATH] [--manifest PATH]
                                    [--output-tsv PATH]

Check MELODIC inputs for duplicates, missing files, inconsistent grids or run
lengths, mask coverage, non-finite summaries, zero variance, and condition count.
USAGE
}

scriptdir="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
maindir="$(dirname "$scriptdir")"
derivdir="${DERIVATIVES_ROOT:-${maindir}/derivatives}"
fsldir="${FSL_OUTPUT_DIR:-${derivdir}/fsl}"
task="${TASK_ID:-rest}"
fwhm="${SMOOTH_FWHM:-5}"
inputlist="${MELODIC_FILELIST:-${fsldir}/melodic_filelist_5mm_denoised.txt}"
manifest="${RUN_MANIFEST:-${fsldir}/task-${task}_run_manifest.tsv}"
outputtsv="${MELODIC_QC_TSV:-${derivdir}/qc/task-${task}_melodic_input_qc.tsv}"

while (($#)); do
    case "$1" in
        --input-list) inputlist="${2:-}"; shift 2 ;;
        --manifest) manifest="${2:-}"; shift 2 ;;
        --output-tsv) outputtsv="${2:-}"; shift 2 ;;
        --help|-h) usage; exit 0 ;;
        *) echo "ERROR: Unknown argument: $1" >&2; usage >&2; exit 1 ;;
    esac
done

[[ -f "$inputlist" ]] || { echo "ERROR: Input list not found: $inputlist" >&2; exit 1; }
[[ -f "$manifest" ]] || { echo "ERROR: Run manifest not found: $manifest" >&2; exit 1; }
for command in fslmaths fslorient fslstats fslval fslnvols; do
    command -v "$command" >/dev/null 2>&1 || {
        echo "ERROR: $command is not on PATH." >&2
        exit 1
    }
done

inputs=()
while IFS= read -r input || [[ -n "$input" ]]; do
    [[ -z "$input" ]] && continue
    inputs+=("$input")
done < "$inputlist"
((${#inputs[@]} > 0)) || { echo "ERROR: Input list is empty: $inputlist" >&2; exit 1; }

duplicates="$(printf '%s\n' "${inputs[@]}" | sort | uniq -d)"
if [[ -n "$duplicates" ]]; then
    echo "ERROR: Duplicate MELODIC inputs:" >&2
    printf '%s\n' "$duplicates" >&2
    exit 1
fi

workdir="$(mktemp -d "${TMPDIR:-/tmp}/r21-melodic-qc.XXXXXX")"
cleanup() { rm -rf "$workdir"; }
trap cleanup EXIT
append_status() {
    if [[ "$status" == "ok" ]]; then
        status="$1"
    else
        status="${status},$1"
    fi
}
mkdir -p "$(dirname "$outputtsv")"
printf 'participant\trun\tcondition\tvolumes\tdim1\tdim2\tdim3\tpixdim1\tpixdim2\tpixdim3\tbrain_mask_voxels\tvarying_voxels\tvarying_fraction\toutside_mask_abs_max\tconfound_columns\tpre_mean_temporal_sd\tpost_mean_temporal_sd\ttemporal_sd_ratio\tdata_min\tdata_max\tdata_mean\tdata_sd\tstatus\tfile\n' >"$outputtsv"

reference_grid=""
reference_volumes=""
failures=0
index=0
for input in "${inputs[@]}"; do
    ((index += 1))
    status="ok"
    if [[ ! -s "$input" ]]; then
        echo "ERROR: Missing MELODIC input: $input" >&2
        failures=1
        continue
    fi

    name="$(basename "$input")"
    participant="unknown"
    run="unknown"
    condition="unknown"
    [[ "$name" =~ ^(sub-[^_]+) ]] && participant="${BASH_REMATCH[1]}"
    [[ "$name" =~ _run-([^_]+) ]] && run="${BASH_REMATCH[1]}"
    [[ "$name" =~ _condition-([^_]+) ]] && condition="${BASH_REMATCH[1]}"

    manifest_row="$(
        awk -F '\t' -v participant="$participant" -v run="$run" '
            NR > 1 && $1 == participant && $2 == run { print; matches++ }
            END { if (matches != 1) exit 1 }
        ' "$manifest"
    )" || manifest_row=""
    if [[ -z "$manifest_row" ]]; then
        echo "ERROR: Expected one manifest row for $participant run-$run" >&2
        failures=1
        continue
    fi
    IFS=$'\t' read -r _participant _run manifest_condition condition_order _events bold confounds <<< "$manifest_row"
    order_padded="$(printf '%02d' "$condition_order")"
    mask="${bold%_desc-preproc_bold.nii.gz}_desc-brain_mask.nii.gz"
    smoothed="${bold%_desc-preproc_bold.nii.gz}_condition-${manifest_condition}_order-${order_padded}_desc-preproc_bold_${fwhm}mm.nii.gz"
    if [[ ! -s "$mask" ]]; then
        echo "ERROR: Missing fMRIPrep brain mask: $mask" >&2
        failures=1
        continue
    fi
    if [[ ! -s "$smoothed" ]]; then
        echo "ERROR: Missing smoothed input: $smoothed" >&2
        failures=1
        continue
    fi
    if [[ ! -s "$confounds" ]]; then
        echo "ERROR: Missing confound matrix: $confounds" >&2
        failures=1
        continue
    fi
    confound_columns="$(awk 'NF { print NF; exit }' "$confounds")"

    volumes="$(fslnvols "$input")"
    dim1="$(fslval "$input" dim1 | tr -d ' ')"
    dim2="$(fslval "$input" dim2 | tr -d ' ')"
    dim3="$(fslval "$input" dim3 | tr -d ' ')"
    pixdim1="$(fslval "$input" pixdim1 | tr -d ' ')"
    pixdim2="$(fslval "$input" pixdim2 | tr -d ' ')"
    pixdim3="$(fslval "$input" pixdim3 | tr -d ' ')"
    sform="$(fslorient -getsform "$input" | tr '\n' ' ' | tr -s ' ' | sed 's/^ //; s/ $//')"
    grid="$dim1,$dim2,$dim3,$pixdim1,$pixdim2,$pixdim3,$sform"

    mask_dim1="$(fslval "$mask" dim1 | tr -d ' ')"
    mask_dim2="$(fslval "$mask" dim2 | tr -d ' ')"
    mask_dim3="$(fslval "$mask" dim3 | tr -d ' ')"
    mask_pixdim1="$(fslval "$mask" pixdim1 | tr -d ' ')"
    mask_pixdim2="$(fslval "$mask" pixdim2 | tr -d ' ')"
    mask_pixdim3="$(fslval "$mask" pixdim3 | tr -d ' ')"
    mask_sform="$(fslorient -getsform "$mask" | tr '\n' ' ' | tr -s ' ' | sed 's/^ //; s/ $//')"
    mask_grid="$mask_dim1,$mask_dim2,$mask_dim3,$mask_pixdim1,$mask_pixdim2,$mask_pixdim3,$mask_sform"
    if [[ "$grid" != "$mask_grid" ]]; then
        append_status "mask_grid_mismatch"
    fi
    if [[ "$condition" != "$manifest_condition" ]]; then
        append_status "condition_mismatch"
    fi

    if [[ -z "$reference_grid" ]]; then
        reference_grid="$grid"
        reference_volumes="$volumes"
    else
        if [[ "$grid" != "$reference_grid" ]]; then
            append_status "grid_mismatch"
        fi
        if [[ "$volumes" != "$reference_volumes" ]]; then
            append_status "volume_mismatch"
        fi
    fi

    pre_temporal_sd="${workdir}/pre_temporal_sd_${index}.nii.gz"
    post_temporal_sd="${workdir}/post_temporal_sd_${index}.nii.gz"
    inside_mask="${workdir}/inside_mask_${index}.nii.gz"
    outside_mask="${workdir}/outside_mask_${index}.nii.gz"
    fslmaths "$smoothed" -Tstd "$pre_temporal_sd"
    fslmaths "$input" -Tstd "$post_temporal_sd"
    read -r brain_mask_voxels _brain_mask_mm3 <<< "$(fslstats "$mask" -V)"
    read -r _pre_varying _pre_mm3 pre_mean_temporal_sd <<< "$(fslstats "$pre_temporal_sd" -V -M)"
    read -r varying_voxels _varying_mm3 post_mean_temporal_sd <<< "$(fslstats "$post_temporal_sd" -V -M)"
    varying_fraction="$(awk -v varying="$varying_voxels" -v mask="$brain_mask_voxels" 'BEGIN { if (mask > 0) printf "%.6f", varying / mask; else print "0" }')"
    temporal_sd_ratio="$(awk -v pre="$pre_mean_temporal_sd" -v post="$post_mean_temporal_sd" 'BEGIN { if (pre > 0) printf "%.6f", post / pre; else print "nan" }')"
    fslmaths "$input" -mas "$mask" "$inside_mask"
    fslmaths "$input" -sub "$inside_mask" -abs -Tmax "$outside_mask"
    read -r _outside_min outside_mask_abs_max <<< "$(fslstats "$outside_mask" -R)"
    read -r data_min data_max data_mean data_sd <<< "$(fslstats "$input" -R -M -S)"
    summaries="$brain_mask_voxels $varying_voxels $varying_fraction $outside_mask_abs_max $confound_columns $pre_mean_temporal_sd $post_mean_temporal_sd $temporal_sd_ratio $data_min $data_max $data_mean $data_sd"
    if grep -Eiq '(^|[[:space:]])(nan|[-+]?inf)([[:space:]]|$)' <<< "$summaries"; then
        append_status "nonfinite_summary"
    fi
    if [[ "$brain_mask_voxels" == "0" ]] || awk -v value="$post_mean_temporal_sd" 'BEGIN { exit !(value <= 0) }'; then
        append_status "empty_or_constant"
    fi
    if awk -v value="$varying_fraction" 'BEGIN { exit !(value < 0.90) }'; then
        append_status "low_mask_coverage"
    fi
    if awk -v value="$outside_mask_abs_max" 'BEGIN { exit !(value > 0.000001) }'; then
        append_status "signal_outside_mask"
    fi
    if awk -v value="$temporal_sd_ratio" 'BEGIN { exit !(value >= 0.995) }'; then
        append_status "no_variance_removed"
    fi
    if awk -v value="$temporal_sd_ratio" 'BEGIN { exit !(value < 0.10) }'; then
        append_status "excessive_variance_removed"
    fi
    if [[ "$participant" == "unknown" || "$run" == "unknown" || "$condition" == "unknown" ]]; then
        append_status "filename_entities"
    fi
    [[ "$status" == "ok" ]] || failures=1

    {
        printf '%s\t' \
            "$participant" "$run" "$condition" "$volumes" \
            "$dim1" "$dim2" "$dim3" "$pixdim1" "$pixdim2" "$pixdim3" \
            "$brain_mask_voxels" "$varying_voxels" "$varying_fraction" \
            "$outside_mask_abs_max" "$confound_columns" \
            "$pre_mean_temporal_sd" "$post_mean_temporal_sd" \
            "$temporal_sd_ratio" "$data_min" "$data_max" "$data_mean" \
            "$data_sd" "$status"
        printf '%s\n' "$input"
    } >>"$outputtsv"
done

bad_subjects="$(
    awk -F '\t' '
        NR > 1 { runs[$1]++; conditions[$1 SUBSEP $3]++ }
        END {
            for (subject in runs) {
                unique = 0
                for (key in conditions) {
                    split(key, fields, SUBSEP)
                    if (fields[1] == subject) unique++
                }
                if (runs[subject] != 4 || unique != 4) print subject, runs[subject], unique
            }
        }
    ' "$outputtsv"
)"
if [[ -n "$bad_subjects" ]]; then
    echo "ERROR: Subjects without exactly four uniquely labeled MELODIC inputs (subject runs conditions):" >&2
    printf '%s\n' "$bad_subjects" >&2
    failures=1
fi

read -r mask_min mask_max <<< "$(
    awk -F '\t' '
        NR > 1 {
            if (!count || $11 < minimum) minimum = $11
            if (!count || $11 > maximum) maximum = $11
            count++
        }
        END { print minimum+0, maximum+0 }
    ' "$outputtsv"
)"
printf 'Inputs checked: %d\n' "${#inputs[@]}"
printf 'Reference volumes per run: %s\n' "$reference_volumes"
printf 'fMRIPrep brain-mask range: %s-%s voxels\n' "$mask_min" "$mask_max"
printf 'Wrote %s\n' "$outputtsv"

if ((failures)); then
    awk -F '\t' '
        NR == 1 {
            for (column = 1; column <= NF; column++) names[$column] = column
            participant = names["participant"]
            run = names["run"]
            condition = names["condition"]
            status = names["status"]
            next
        }
        $status != "ok" {
            failed++
            if (failed <= 20) rows[failed] = $participant "\trun-" $run "\t" $condition "\t" $status
            count = split($status, labels, ",")
            for (i = 1; i <= count; i++) totals[labels[i]]++
        }
        END {
            print "Failure counts:" > "/dev/stderr"
            for (label in totals) print "  " label ": " totals[label] > "/dev/stderr"
            print "Failed inputs (first 20):" > "/dev/stderr"
            for (i = 1; i <= failed && i <= 20; i++) print "  " rows[i] > "/dev/stderr"
            if (failed > 20) print "  ... " failed - 20 " more; see the TSV" > "/dev/stderr"
        }
    ' "$outputtsv"
    echo "ERROR: One or more MELODIC input checks failed." >&2
    exit 1
fi
echo "MELODIC inputs passed all checks." >&2
