#!/usr/bin/env python3
"""Audit primary randomise outputs and collect significant corrected-p maps."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from collections import OrderedDict
from pathlib import Path


CONTRASTS = (
    "both-minus-sham",
    "both-minus-rtpj",
    "both-minus-vlpfc",
    "rtpj-minus-vlpfc",
    "rtpj-minus-sham",
    "vlpfc-minus-sham",
    "both-minus-mean-rtpj-vlpfc",
)
PRIMARY_NETWORKS = {
    "default_mode": "dmn",
    "executive_control": "ecn",
    "right_frontoparietal": "right-fpn",
    "left_frontoparietal": "left-fpn",
}
DIRECTIONS = ((1, "positive"), (2, "negative"))
CLUSTER_METHOD = ("cluster-extent", "clustere_corrp")
TFCE_METHOD = ("tfce", "tfce_corrp")
SUMMARY_FIELDS = (
    "sensitivity_label",
    "excluded_participants",
    "analysis",
    "network",
    "component",
    "condition_contrast",
    "design_contrast",
    "direction",
    "inference",
    "design_con_valid",
    "group_input_exists",
    "expected_participants",
    "group_input_volumes",
    "group_input_complete",
    "completion_marker_exists",
    "tstat_exists",
    "corrp_exists",
    "peak_corrp",
    "peak_gt_threshold",
    "status",
    "corrp_file",
    "copied_image",
    "copied_sidecar",
    "roi_values_tsv",
)
ROI_VALUE_FIELDS = (
    "sensitivity_label",
    "analysis",
    "network",
    "component",
    "condition_contrast",
    "direction",
    "participant",
    "run",
    "condition",
    "dual_regression_label",
    "stage2_beta",
)


def parse_args() -> argparse.Namespace:
    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent
    derivatives = project_root / "derivatives"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--network-set", choices=("dmn", "primary"), default="primary")
    parser.add_argument(
        "--analysis-set",
        choices=("ica", "smith09", "all"),
        default="all",
        help="Audit data-derived ICA, direct Smith09 maps, or both (default: all).",
    )
    parser.add_argument(
        "--include-tfce",
        action="store_true",
        help="Also audit TFCE outputs. Cluster extent is the default.",
    )
    parser.add_argument("--map-type", choices=("beta", "z"), default="beta")
    parser.add_argument(
        "--sensitivity-label",
        help="Audit outputs under contrasts/sensitivity-LABEL.",
    )
    parser.add_argument(
        "--exclude-list",
        type=Path,
        help="Participant list used for the labeled sensitivity analysis.",
    )
    parser.add_argument("--threshold", type=float, default=0.95)
    parser.add_argument("--task", default="rest")
    parser.add_argument("--space", default="MNI152NLin6Asym")
    parser.add_argument(
        "--fsl-dir",
        type=Path,
        default=derivatives / "fsl",
        help="Project FSL derivatives directory.",
    )
    parser.add_argument(
        "--comparison",
        type=Path,
        help="Smith09 ICA comparison TSV (default: FSL diagnostics directory).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Tracked summary directory (default: FSL randomise_summary directory).",
    )
    parser.add_argument("--no-copy", action="store_true", help="Do not copy significant maps.")
    parser.add_argument(
        "--fail-on-missing",
        action="store_true",
        help="Exit nonzero when expected inputs or outputs are missing or invalid.",
    )
    return parser.parse_args()


def analysis_label(analysis: str) -> str:
    return {
        "smith09": "smith09_denoised",
        "0": "denoised_dim-00_task-rest",
        "20": "denoised_dim-20_task-rest",
    }[analysis]


def build_ica_component_plan(path: Path, network_set: str) -> list[dict[str, object]]:
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        required = {
            "data_set",
            "dimension",
            "network",
            "analysis_priority",
            "best_component",
        }
        missing = required.difference(reader.fieldnames or ())
        if missing:
            raise ValueError(f"Smith09 comparison is missing columns: {sorted(missing)}")

        plan: OrderedDict[tuple[str, int], dict[str, object]] = OrderedDict()
        for row in reader:
            if row["data_set"] != "denoised" or row["analysis_priority"] != "primary":
                continue
            if network_set == "dmn" and row["network"] != "default_mode":
                continue
            network = PRIMARY_NETWORKS.get(row["network"])
            if network is None:
                continue
            analysis = {"automatic": "0", "20": "20"}.get(row["dimension"])
            if analysis is None:
                continue
            component = int(row["best_component"])
            key = (analysis, component)
            if key not in plan:
                plan[key] = {
                    "analysis": analysis,
                    "component": component,
                    "network": network,
                }
            elif {str(plan[key]["network"]), network} == {"right-fpn", "left-fpn"}:
                plan[key]["network"] = "bilateral-fpn"
            elif plan[key]["network"] != network:
                plan[key]["network"] = f"{plan[key]['network']}-{network}"

    if not plan:
        raise ValueError("No matching denoised primary components were found.")
    return list(plan.values())


def build_component_plan(
    path: Path, network_set: str, analysis_set: str
) -> list[dict[str, object]]:
    plan: list[dict[str, object]] = []
    if analysis_set in {"ica", "all"}:
        plan.extend(build_ica_component_plan(path, network_set))
    if analysis_set in {"smith09", "all"}:
        smith09 = (
            ("dmn", 4),
            ("ecn", 8),
            ("right-fpn", 9),
            ("left-fpn", 10),
        )
        for network, component in smith09:
            if network_set == "dmn" and network != "dmn":
                continue
            plan.append(
                {"analysis": "smith09", "component": component, "network": network}
            )
    if not plan:
        raise ValueError("No randomise components matched the requested analysis set.")
    return plan


def verify_design_con(path: Path) -> bool:
    if not path.is_file():
        return False
    lines = [line.strip() for line in path.read_text().splitlines()]
    try:
        matrix_start = lines.index("/Matrix") + 1
    except ValueError:
        return False
    matrix = [line for line in lines[matrix_start:] if line]
    return matrix == ["1", "-1"]


def peak_value(path: Path, fslstats: str) -> float:
    result = subprocess.run(
        [fslstats, str(path), "-R"],
        text=True,
        capture_output=True,
        check=True,
    )
    values = result.stdout.split()
    if len(values) < 2:
        raise ValueError(f"Unexpected fslstats output: {result.stdout!r}")
    peak = float(values[-1])
    if not math.isfinite(peak):
        raise ValueError(f"Non-finite fslstats maximum: {peak}")
    if not 0.0 <= peak <= 1.0:
        raise ValueError(f"Corrected 1-p maximum is outside [0, 1]: {peak}")
    return peak


def volume_count(path: Path, fslnvols: str) -> int:
    result = subprocess.run(
        [fslnvols, str(path)],
        text=True,
        capture_output=True,
        check=True,
    )
    return int(result.stdout.strip())


def subject_count(path: Path) -> int:
    with path.open(newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    if not rows or "participant" not in rows[0]:
        raise ValueError(f"Invalid subject-order table: {path}")
    return len(rows)


def read_exclusions(path: Path | None) -> list[str]:
    if path is None:
        return []
    exclusions: list[str] = []
    for line in path.read_text().splitlines():
        label = line.split("#", 1)[0].strip()
        if not label:
            continue
        if not re.fullmatch(r"sub-[A-Za-z0-9]+", label):
            raise ValueError(f"Invalid participant in exclusion list: {label}")
        if label in exclusions:
            raise ValueError(f"Duplicate participant in exclusion list: {label}")
        exclusions.append(label)
    if not exclusions:
        raise ValueError(f"Exclusion list is empty: {path}")
    return exclusions


def read_input_order(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        required = {
            "dual_regression_label",
            "participant",
            "run",
            "condition",
        }
        missing = required.difference(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path} is missing columns: {sorted(missing)}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"Input-order table is empty: {path}")

    expected_conditions = {"sham", "rtpj", "vlpfc", "both"}
    participant_conditions: dict[str, set[str]] = {}
    seen: set[tuple[str, str]] = set()
    for row in rows:
        participant = row["participant"]
        condition = row["condition"].lower()
        key = (participant, condition)
        if not participant or condition not in expected_conditions:
            raise ValueError(f"Invalid participant or condition in {path}: {row}")
        if key in seen:
            raise ValueError(f"Duplicate {participant} {condition} row in {path}")
        seen.add(key)
        participant_conditions.setdefault(participant, set()).add(condition)
        row["condition"] = condition
    incomplete = {
        participant: sorted(expected_conditions.difference(conditions))
        for participant, conditions in participant_conditions.items()
        if conditions != expected_conditions
    }
    if incomplete:
        raise ValueError(f"Incomplete participant conditions in {path}: {incomplete}")
    return rows


def relative_path(path: Path, project_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(project_root.resolve()))
    except ValueError:
        return str(path.resolve())


def camel_label(value: str) -> str:
    words = [word for word in re.split(r"[^A-Za-z0-9]+", value) if word]
    return "".join(word[:1].upper() + word[1:] for word in words)


def copied_name(
    task: str,
    space: str,
    analysis: str,
    network: str,
    component: int,
    contrast: str,
    direction: str,
    method: str,
    sensitivity_label: str,
) -> str:
    dimension = {
        "0": "dim00",
        "20": "dim20",
        "smith09": "smith09",
    }[analysis]
    sensitivity = camel_label(sensitivity_label) if sensitivity_label else ""
    description = (
        f"{sensitivity}"
        f"{dimension}{camel_label(network)}Comp{component:04d}"
        f"{camel_label(contrast)}{camel_label(direction)}{camel_label(method)}Corrp"
    )
    return (
        f"task-{task}_space-{space}_desc-{description}_stat-corrp_statmap.nii.gz"
    )


def roi_values_name(copied_image: Path) -> str:
    stem = copied_image.name.removesuffix("_stat-corrp_statmap.nii.gz")
    return f"{stem}_stat-stage2Beta_timeseries.tsv"


def extract_roi_values(
    corrp: Path,
    threshold: float,
    dr_dir: Path,
    component: int,
    map_type: str,
    destination: Path,
    metadata: dict[str, str],
    excluded_participants: set[str],
    fslmaths: str,
    fslroi: str,
    fslstats: str,
) -> int:
    input_order = read_input_order(dr_dir / "input_order.tsv")
    stage2_suffix = "" if map_type == "beta" else "_Z"
    component_index = component - 1
    extracted: list[dict[str, str]] = []

    with tempfile.TemporaryDirectory(prefix="r21_randomise_roi_") as temporary:
        temporary_dir = Path(temporary)
        roi_mask = temporary_dir / "roi_mask.nii.gz"
        subprocess.run(
            [
                fslmaths,
                str(corrp),
                "-thr",
                repr(math.nextafter(threshold, math.inf)),
                "-bin",
                str(roi_mask),
            ],
            check=True,
        )
        component_image = temporary_dir / "component.nii.gz"
        for item in input_order:
            if item["participant"] in excluded_participants:
                continue
            source = dr_dir / (
                f"dr_stage2_{item['dual_regression_label']}{stage2_suffix}.nii.gz"
            )
            if not source.is_file():
                raise FileNotFoundError(f"Stage-2 image not found: {source}")
            subprocess.run(
                [fslroi, str(source), str(component_image), str(component_index), "1"],
                check=True,
            )
            result = subprocess.run(
                [fslstats, str(component_image), "-k", str(roi_mask), "-m"],
                text=True,
                capture_output=True,
                check=True,
            )
            value = float(result.stdout.strip())
            if not math.isfinite(value):
                raise ValueError(f"Non-finite ROI mean for {source}: {value}")
            extracted.append(
                {
                    **metadata,
                    "participant": item["participant"],
                    "run": item["run"],
                    "condition": item["condition"],
                    "dual_regression_label": item["dual_regression_label"],
                    "stage2_beta": f"{value:.10g}",
                }
            )

    with destination.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=ROI_VALUE_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(extracted)
    return len(extracted)


def read_marker(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    metadata: dict[str, str] = {}
    for line in path.read_text().splitlines():
        key, separator, value = line.partition("\t")
        if separator:
            metadata[key] = value
    return metadata


def write_sidecar(
    path: Path,
    source: Path,
    project_root: Path,
    row: dict[str, str],
    marker: dict[str, str],
    task: str,
    threshold: float,
    cluster_threshold: float,
    roi_values: Path,
    sensitivity_label: str,
    excluded_participants: list[str],
) -> None:
    payload = {
        "Description": "FSL randomise FWE-corrected 1-p statistical map",
        "TaskName": task,
        "AnalysisDimension": row["analysis"],
        "Network": row["network"],
        "Component": int(row["component"]),
        "ConditionContrast": row["condition_contrast"],
        "DesignContrast": row["design_contrast"],
        "Direction": row["direction"],
        "InferenceMethod": row["inference"],
        "PeakOneMinusP": float(row["peak_corrp"]),
        "SignificanceThresholdOneMinusP": threshold,
        "ClusterFormingTThreshold": cluster_threshold,
        "NumberOfPermutations": int(marker.get("n_perm", "5000")),
        "Sources": [relative_path(source, project_root)],
        "ROIValues": relative_path(roi_values, project_root),
        "SensitivityLabel": sensitivity_label or None,
        "ExcludedParticipants": excluded_participants,
        "GeneratedBy": [{"Name": "FSL randomise"}],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def main() -> int:
    args = parse_args()
    if not 0.0 <= args.threshold <= 1.0:
        raise ValueError("--threshold must be between 0 and 1.")
    if bool(args.sensitivity_label) != bool(args.exclude_list):
        raise ValueError("--sensitivity-label and --exclude-list must be used together.")
    if args.sensitivity_label and not re.fullmatch(
        r"[a-z0-9][a-z0-9-]*", args.sensitivity_label
    ):
        raise ValueError("--sensitivity-label must contain lowercase letters, numbers, or hyphens.")
    project_root = Path(__file__).resolve().parent.parent
    exclusions = read_exclusions(args.exclude_list.resolve() if args.exclude_list else None)
    fsl_dir = args.fsl_dir.resolve()
    comparison = (
        args.comparison.resolve()
        if args.comparison
        else fsl_dir / "diagnostics" / "smith09_ica_comparison.tsv"
    )
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir
        else fsl_dir / "randomise_summary"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_description = (
        f"_desc-{camel_label(args.sensitivity_label)}" if args.sensitivity_label else ""
    )
    output_tsv = output_dir / (
        f"task-{args.task}{summary_description}_randomise_peak_summary.tsv"
    )

    plan = build_component_plan(comparison, args.network_set, args.analysis_set)
    methods = [CLUSTER_METHOD]
    if args.include_tfce:
        methods.append(TFCE_METHOD)
    fslstats = shutil.which("fslstats")
    fslnvols = shutil.which("fslnvols")
    fslmaths = shutil.which("fslmaths")
    fslroi = shutil.which("fslroi")
    required_commands = {
        "fslstats": fslstats,
        "fslnvols": fslnvols,
    }
    if not args.no_copy:
        required_commands.update({"fslmaths": fslmaths, "fslroi": fslroi})
    missing_commands = [name for name, path in required_commands.items() if path is None]
    if missing_commands:
        raise RuntimeError(f"Required FSL commands are not on PATH: {missing_commands}")
    assert fslstats is not None and fslnvols is not None

    rows: list[dict[str, str]] = []
    missing_paths: set[Path] = set()
    peak_errors: list[str] = []
    validation_errors: list[str] = []
    valid_designs = 0
    marker_count = 0
    tstat_count = 0
    corrp_count = 0
    significant_count = 0
    copied_count = 0
    roi_values_count = 0
    roi_value_rows = 0
    roi_errors: list[str] = []
    significant_by_method = {method: 0 for method, _suffix in methods}

    for item in plan:
        analysis = str(item["analysis"])
        network = str(item["network"])
        component = int(item["component"])
        component_padded = f"{component:04d}"
        dr_dir = fsl_dir / f"dual-regression_{analysis_label(analysis)}.dr"
        contrast_root = dr_dir / "contrasts"
        if args.sensitivity_label:
            contrast_root = contrast_root / f"sensitivity-{args.sensitivity_label}"
        component_dir = contrast_root / f"component-{component_padded}_stat-{args.map_type}"
        design_con = component_dir / "design.con"
        design_valid = verify_design_con(design_con)
        if design_valid:
            valid_designs += 1
        else:
            missing_paths.add(design_con)
        component_inputs_complete = design_valid
        for required_name in ("design.mat", "design.grp"):
            required = component_dir / required_name
            if not required.is_file():
                missing_paths.add(required)
                component_inputs_complete = False
        subject_order = component_dir / "subject_order.tsv"
        expected_participants: int | None = None
        if subject_order.is_file():
            try:
                expected_participants = subject_count(subject_order)
            except (OSError, ValueError) as error:
                validation_errors.append(str(error))
                component_inputs_complete = False
        else:
            missing_paths.add(subject_order)
            component_inputs_complete = False
        mask = dr_dir / "mask.nii.gz"
        if not mask.is_file():
            missing_paths.add(mask)
            component_inputs_complete = False

        for contrast in CONTRASTS:
            contrast_dir = component_dir / contrast
            group_input = contrast_dir / (
                f"group_task-{args.task}_component-{component_padded}_stat-{args.map_type}_"
                f"contrast-{contrast}.nii.gz"
            )
            group_exists = group_input.is_file()
            group_volumes: int | None = None
            group_complete = False
            if not group_exists:
                missing_paths.add(group_input)
            elif expected_participants is not None:
                try:
                    group_volumes = volume_count(group_input, fslnvols)
                    group_complete = group_volumes == expected_participants
                    if not group_complete:
                        validation_errors.append(
                            f"{group_input}: {group_volumes} volumes; "
                            f"expected {expected_participants}"
                        )
                except (OSError, subprocess.CalledProcessError, ValueError) as error:
                    validation_errors.append(f"{group_input}: {error}")
            randomise_dir = component_dir / "randomise" / f"network-{network}"
            prefix = randomise_dir / (
                f"task-{args.task}_network-{network}_component-{component_padded}_"
                f"stat-{args.map_type}_contrast-{contrast}"
            )
            marker_path = Path(f"{prefix}.complete")
            marker_exists = marker_path.is_file()
            marker = read_marker(marker_path)
            marker_count += int(marker_exists)

            tstats = {
                number: Path(f"{prefix}_tstat{number}.nii.gz")
                for number, _direction in DIRECTIONS
            }
            for tstat in tstats.values():
                if tstat.is_file():
                    tstat_count += 1
                else:
                    missing_paths.add(tstat)

            for number, direction in DIRECTIONS:
                for method, suffix in methods:
                    corrp = Path(f"{prefix}_{suffix}_tstat{number}.nii.gz")
                    corrp_exists = corrp.is_file()
                    if corrp_exists:
                        corrp_count += 1
                    else:
                        missing_paths.add(corrp)
                    status = "ok"
                    peak: float | None = None
                    if corrp_exists:
                        try:
                            peak = peak_value(corrp, fslstats)
                        except (OSError, subprocess.CalledProcessError, ValueError) as error:
                            status = "peak_error"
                            peak_errors.append(f"{corrp}: {error}")
                    else:
                        status = "missing_corrp"

                    if not component_inputs_complete:
                        status = "invalid_component_inputs"
                    elif not group_complete:
                        status = "invalid_group_input"
                    elif not tstats[number].is_file():
                        status = "missing_tstat"

                    significant = peak is not None and peak > args.threshold
                    if significant:
                        significant_count += 1
                        significant_by_method[method] += 1
                    row = {
                        "sensitivity_label": args.sensitivity_label or "none",
                        "excluded_participants": ",".join(exclusions),
                        "analysis": analysis,
                        "network": network,
                        "component": str(component),
                        "condition_contrast": contrast,
                        "design_contrast": f"C{number}",
                        "direction": direction,
                        "inference": method,
                        "design_con_valid": str(design_valid).lower(),
                        "group_input_exists": str(group_exists).lower(),
                        "expected_participants": (
                            "n/a" if expected_participants is None else str(expected_participants)
                        ),
                        "group_input_volumes": (
                            "n/a" if group_volumes is None else str(group_volumes)
                        ),
                        "group_input_complete": str(group_complete).lower(),
                        "completion_marker_exists": str(marker_exists).lower(),
                        "tstat_exists": str(tstats[number].is_file()).lower(),
                        "corrp_exists": str(corrp_exists).lower(),
                        "peak_corrp": "n/a" if peak is None else f"{peak:.8g}",
                        "peak_gt_threshold": str(significant).lower(),
                        "status": status,
                        "corrp_file": relative_path(corrp, project_root),
                        "copied_image": "",
                        "copied_sidecar": "",
                        "roi_values_tsv": "",
                    }

                    scientifically_complete = (
                        component_inputs_complete
                        and group_complete
                        and tstats[number].is_file()
                        and corrp_exists
                        and status == "ok"
                    )
                    if significant and scientifically_complete and not args.no_copy:
                        destination = output_dir / copied_name(
                            args.task,
                            args.space,
                            analysis,
                            network,
                            component,
                            contrast,
                            direction,
                            method,
                            args.sensitivity_label or "",
                        )
                        sidecar = destination.with_name(destination.name.removesuffix(".nii.gz") + ".json")
                        roi_values = output_dir / roi_values_name(destination)
                        shutil.copy2(corrp, destination)
                        row["copied_image"] = relative_path(destination, project_root)
                        row["copied_sidecar"] = relative_path(sidecar, project_root)
                        row["roi_values_tsv"] = relative_path(roi_values, project_root)
                        try:
                            extracted_rows = extract_roi_values(
                                corrp,
                                args.threshold,
                                dr_dir,
                                component,
                                args.map_type,
                                roi_values,
                                {
                                    "sensitivity_label": args.sensitivity_label or "none",
                                    "analysis": analysis,
                                    "network": network,
                                    "component": str(component),
                                    "condition_contrast": contrast,
                                    "direction": direction,
                                },
                                set(exclusions),
                                str(fslmaths),
                                str(fslroi),
                                fslstats,
                            )
                            write_sidecar(
                                sidecar,
                                corrp,
                                project_root,
                                row,
                                marker,
                                args.task,
                                args.threshold,
                                float(marker.get("cluster_threshold", "3.1")),
                                roi_values,
                                args.sensitivity_label or "",
                                exclusions,
                            )
                            copied_count += 1
                            roi_values_count += 1
                            roi_value_rows += extracted_rows
                        except (OSError, subprocess.CalledProcessError, ValueError) as error:
                            row["status"] = "roi_export_error"
                            row["roi_values_tsv"] = ""
                            roi_values.unlink(missing_ok=True)
                            sidecar.unlink(missing_ok=True)
                            roi_errors.append(f"{corrp}: {error}")
                    rows.append(row)

    with output_tsv.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=SUMMARY_FIELDS, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)

    (output_dir / "README.md").write_text(
        "# Randomise Summary\n\n"
        "Generated by `code/check_randomise_results.py`. FSL corrected-p images "
        "store `1-p`; therefore values greater than 0.95 correspond to corrected "
        "p-values below 0.05. By default, the TSV contains cluster-extent "
        "maps for positive (C1) and negative (C2) directions; TFCE is included "
        "only when explicitly requested. "
        "NIfTI files and JSON sidecars are copied here only when the map is "
        "complete and its peak exceeds the configured threshold. Each copied "
        "map also has a small tracked timeseries TSV containing participant-by-"
        "condition stage-2 beta values for portable notebook plotting.\n"
    )

    jobs = len(plan) * len(CONTRASTS)
    expected_tstats = jobs * len(DIRECTIONS)
    expected_corrp = jobs * len(DIRECTIONS) * len(methods)
    print(f"Components checked: {len(plan)}")
    print(f"Sensitivity label: {args.sensitivity_label or 'none'}")
    print(f"Excluded participants: {','.join(exclusions) if exclusions else 'none'}")
    print(f"Randomise jobs checked: {jobs}")
    print(f"Design contrasts verified (+1/-1): {valid_designs}/{len(plan)}")
    print(f"Completion markers present: {marker_count}/{jobs}")
    print(f"t-stat images present: {tstat_count}/{expected_tstats}")
    print(f"corrp images present: {corrp_count}/{expected_corrp}")
    if args.include_tfce:
        print(f"TFCE maps with peak > {args.threshold:g}: {significant_by_method['tfce']}")
    print(
        f"Cluster-extent maps with peak > {args.threshold:g}: "
        f"{significant_by_method['cluster-extent']}"
    )
    print(f"Significant maps copied: {copied_count}/{significant_count}")
    print(f"ROI-value TSVs written: {roi_values_count} ({roi_value_rows} rows)")
    print(f"Missing or invalid required paths: {len(missing_paths)}")
    print(f"Input-validation errors: {len(validation_errors)}")
    print(f"Peak-read errors: {len(peak_errors)}")
    print(f"ROI-export errors: {len(roi_errors)}")
    print(f"Wrote {output_tsv}")
    for path in sorted(missing_paths, key=str)[:20]:
        print(f"MISSING: {path}", file=sys.stderr)
    if len(missing_paths) > 20:
        print(f"... and {len(missing_paths) - 20} more missing paths", file=sys.stderr)
    for error in peak_errors[:20]:
        print(f"ERROR: {error}", file=sys.stderr)
    for error in validation_errors[:20]:
        print(f"ERROR: {error}", file=sys.stderr)
    for error in roi_errors[:20]:
        print(f"ERROR: {error}", file=sys.stderr)

    incomplete = bool(
        missing_paths
        or peak_errors
        or validation_errors
        or roi_errors
        or valid_designs != len(plan)
    )
    return 1 if args.fail_on_missing and incomplete else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
