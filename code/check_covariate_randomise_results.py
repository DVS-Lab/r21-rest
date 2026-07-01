#!/usr/bin/env python3
"""Compile covariate-adjusted randomise outputs and extract significant ROIs."""

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
from pathlib import Path


CLUSTER_METHOD = ("cluster-extent", "clustere_corrp")
TFCE_METHOD = ("tfce", "tfce_corrp")
SUMMARY_FIELDS = (
    "model_label",
    "covariates",
    "analysis",
    "network",
    "component",
    "map_type",
    "condition_contrast",
    "design_contrast",
    "contrast_name",
    "direction",
    "tested_covariate",
    "contrast_vector",
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
    "group_input",
    "design_mat",
    "design_con",
    "corrp_file",
    "copied_image",
    "copied_sidecar",
    "roi_values_tsv",
    "condition_values_tsv",
)
CONDITION_VALUE_FIELDS = (
    "model_label",
    "analysis",
    "network",
    "component",
    "map_type",
    "condition_contrast",
    "design_contrast",
    "contrast_name",
    "direction",
    "tested_covariate",
    "participant",
    "run",
    "condition",
    "dual_regression_label",
    "stage2_beta",
)


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]
    derivatives = project_root / "derivatives"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models",
        default="fdmean-blink,fdmean-pupil",
        help="Comma-separated model labels, with or without model-/cov- prefixes.",
    )
    parser.add_argument("--threshold", type=float, default=0.95)
    parser.add_argument("--task", default="rest")
    parser.add_argument("--space", default="MNI152NLin6Asym")
    parser.add_argument("--include-tfce", action="store_true")
    parser.add_argument("--no-copy", action="store_true", help="Do not copy significant maps or extract ROI values.")
    parser.add_argument(
        "--fsl-dir",
        type=Path,
        default=derivatives / "fsl",
        help="Project FSL derivatives directory.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Tracked summary directory (default: derivatives/fsl/covariate_randomise_summary).",
    )
    parser.add_argument(
        "--fail-on-missing",
        action="store_true",
        help="Exit nonzero if expected inputs or outputs are missing or invalid.",
    )
    return parser.parse_args()


def normalize_models(value: str) -> list[str]:
    models: list[str] = []
    for item in value.split(","):
        model = item.strip()
        if not model:
            continue
        if model.startswith("model-"):
            model = model.removeprefix("model-")
        if not model.startswith("cov-"):
            model = f"cov-{model}"
        if not re.fullmatch(r"cov-[a-z0-9][a-z0-9-]*", model):
            raise ValueError(f"Invalid model label: {model}")
        if model not in models:
            models.append(model)
    if not models:
        raise ValueError("No models requested.")
    return models


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def relative_path(path: Path, project_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(project_root.resolve()))
    except ValueError:
        return str(path.resolve())


def camel_label(value: str) -> str:
    words = [word for word in re.split(r"[^A-Za-z0-9]+", value) if word]
    return "".join(word[:1].upper() + word[1:] for word in words)


def parse_component_dir(path: Path) -> tuple[str, str, str]:
    match = re.fullmatch(r"component-(\d+)_stat-([A-Za-z0-9]+)", path.name)
    if not match:
        raise ValueError(f"Cannot parse component directory: {path}")
    dr_dir = path.parent.parent
    analysis = dr_dir.name.removeprefix("dual-regression_").removesuffix(".dr")
    return analysis, match.group(1), match.group(2)


def parse_design_con(path: Path) -> tuple[bool, list[dict[str, object]], int]:
    if not path.is_file():
        return False, [], 0
    contrast_names: dict[int, str] = {}
    num_waves: int | None = None
    num_contrasts: int | None = None
    matrix: list[list[str]] = []
    in_matrix = False
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if in_matrix:
            matrix.append(line.split())
            continue
        if line == "/Matrix":
            in_matrix = True
            continue
        parts = line.split()
        if not parts:
            continue
        if parts[0].startswith("/ContrastName"):
            try:
                number = int(parts[0].removeprefix("/ContrastName"))
            except ValueError:
                continue
            contrast_names[number] = parts[1] if len(parts) > 1 else f"C{number}"
        elif parts[0] == "/NumWaves" and len(parts) > 1:
            num_waves = int(parts[1])
        elif parts[0] == "/NumContrasts" and len(parts) > 1:
            num_contrasts = int(parts[1])

    valid = (
        num_waves is not None
        and num_contrasts is not None
        and num_contrasts == 4
        and num_contrasts == len(matrix)
        and all(len(row) == num_waves for row in matrix)
    )
    contrasts: list[dict[str, object]] = []
    for index, vector in enumerate(matrix, start=1):
        contrasts.append(
            {
                "number": index,
                "name": contrast_names.get(index, f"C{index}"),
                "vector": vector,
            }
        )
    return valid, contrasts, num_waves or 0


def covariates_from_audit(path: Path) -> list[str]:
    if not path.is_file():
        return []
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        fields = reader.fieldnames or []
    return [
        field
        for field in fields
        if field not in {"randomise_index", "participant"}
        and not field.endswith("_demeaned")
    ]


def read_audit(path: Path) -> list[dict[str, str]]:
    rows = read_tsv(path)
    if not rows:
        raise ValueError(f"Covariate audit is empty: {path}")
    rows = sorted(rows, key=lambda row: int(row["randomise_index"]))
    participants = [row["participant"] for row in rows]
    if len(participants) != len(set(participants)):
        raise ValueError(f"Covariate audit has duplicate participants: {path}")
    return rows


def vector_label(vector: list[str], covariates: list[str]) -> tuple[str, str]:
    numbers = [float(value) for value in vector]
    nonzero = [index for index, value in enumerate(numbers) if abs(value) > 1e-12]
    if not nonzero:
        return "none", ""
    if nonzero == [0]:
        return "positive" if numbers[0] > 0 else "negative", "intercept"
    if len(nonzero) == 1:
        index = nonzero[0]
        covariate = covariates[index - 1] if 0 < index <= len(covariates) else f"EV{index + 1}"
        return "positive" if numbers[index] > 0 else "negative", covariate
    return "custom", ",".join(str(index + 1) for index in nonzero)


def peak_value(path: Path, fslstats: str) -> float:
    result = subprocess.run([fslstats, str(path), "-R"], text=True, capture_output=True, check=True)
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
    result = subprocess.run([fslnvols, str(path)], text=True, capture_output=True, check=True)
    return int(result.stdout.strip())


def copied_name(
    task: str,
    space: str,
    analysis: str,
    model_label: str,
    network: str,
    component: str,
    contrast: str,
    contrast_name: str,
    method: str,
) -> str:
    description = (
        f"{camel_label(analysis)}"
        f"{camel_label(model_label)}"
        f"{camel_label(network)}"
        f"Comp{component}"
        f"{camel_label(contrast)}"
        f"{camel_label(contrast_name)}"
        f"{camel_label(method)}Corrp"
    )
    return f"task-{task}_space-{space}_desc-{description}_stat-corrp_statmap.nii.gz"


def roi_values_name(copied_image: Path) -> str:
    stem = copied_image.name.removesuffix("_stat-corrp_statmap.nii.gz")
    return f"{stem}_stat-subjectContrast_values.tsv"


def condition_values_name(copied_image: Path) -> str:
    stem = copied_image.name.removesuffix("_stat-corrp_statmap.nii.gz")
    return f"{stem}_stat-stage2Beta_timeseries.tsv"


def read_input_order(path: Path) -> list[dict[str, str]]:
    rows = read_tsv(path)
    if not rows:
        raise ValueError(f"Input-order table is empty: {path}")
    required = {"dual_regression_label", "participant", "run", "condition"}
    missing = required.difference(rows[0])
    if missing:
        raise ValueError(f"{path} is missing columns: {sorted(missing)}")
    expected_conditions = {"sham", "rtpj", "vlpfc", "both"}
    seen: set[tuple[str, str]] = set()
    for row in rows:
        row["condition"] = row["condition"].lower()
        key = (row["participant"], row["condition"])
        if not row["participant"] or row["condition"] not in expected_conditions:
            raise ValueError(f"Invalid participant or condition in {path}: {row}")
        if key in seen:
            raise ValueError(f"Duplicate {row['participant']} {row['condition']} row in {path}")
        seen.add(key)
    return rows


def extract_roi_values(
    corrp: Path,
    threshold: float,
    group_input: Path,
    audit_rows: list[dict[str, str]],
    destination: Path,
    metadata: dict[str, str],
    fslmaths: str,
    fslroi: str,
    fslstats: str,
) -> int:
    covariate_fields = [
        field
        for field in audit_rows[0]
        if field not in {"randomise_index", "participant"}
    ]
    fieldnames = [
        *metadata.keys(),
        "randomise_index",
        "participant",
        "subject_contrast_beta",
        *covariate_fields,
    ]
    rows: list[dict[str, str]] = []
    with tempfile.TemporaryDirectory(prefix="r21_covariate_randomise_roi_") as temporary:
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
        subject_volume = temporary_dir / "subject_contrast.nii.gz"
        for index, audit_row in enumerate(audit_rows):
            subprocess.run([fslroi, str(group_input), str(subject_volume), str(index), "1"], check=True)
            result = subprocess.run(
                [fslstats, str(subject_volume), "-k", str(roi_mask), "-m"],
                text=True,
                capture_output=True,
                check=True,
            )
            value = float(result.stdout.strip())
            if not math.isfinite(value):
                raise ValueError(f"Non-finite ROI mean for {group_input} volume {index}: {value}")
            row = {
                **metadata,
                "randomise_index": audit_row["randomise_index"],
                "participant": audit_row["participant"],
                "subject_contrast_beta": f"{value:.10g}",
            }
            for field in covariate_fields:
                row[field] = audit_row[field]
            rows.append(row)
    write_tsv(destination, rows, fieldnames)
    return len(rows)


def extract_condition_values(
    corrp: Path,
    threshold: float,
    dr_dir: Path,
    component: int,
    map_type: str,
    audit_rows: list[dict[str, str]],
    destination: Path,
    metadata: dict[str, str],
    fslmaths: str,
    fslroi: str,
    fslstats: str,
) -> int:
    included_participants = {row["participant"] for row in audit_rows}
    stage2_suffix = "" if map_type == "beta" else "_Z"
    component_index = component - 1
    rows: list[dict[str, str]] = []
    participant_conditions: dict[str, set[str]] = {
        participant: set() for participant in included_participants
    }

    with tempfile.TemporaryDirectory(prefix="r21_covariate_randomise_condition_roi_") as temporary:
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
        for item in read_input_order(dr_dir / "input_order.tsv"):
            if item["participant"] not in included_participants:
                continue
            source = dr_dir / f"dr_stage2_{item['dual_regression_label']}{stage2_suffix}.nii.gz"
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
            participant_conditions[item["participant"]].add(item["condition"])
            rows.append(
                {
                    **metadata,
                    "participant": item["participant"],
                    "run": item["run"],
                    "condition": item["condition"],
                    "dual_regression_label": item["dual_regression_label"],
                    "stage2_beta": f"{value:.10g}",
                }
            )

    expected_conditions = {"sham", "rtpj", "vlpfc", "both"}
    incomplete = {
        participant: sorted(expected_conditions.difference(conditions))
        for participant, conditions in participant_conditions.items()
        if conditions != expected_conditions
    }
    if incomplete:
        raise ValueError(f"Incomplete condition ROI values: {incomplete}")
    write_tsv(destination, rows, list(CONDITION_VALUE_FIELDS))
    return len(rows)


def write_sidecar(
    path: Path,
    row: dict[str, str],
    task: str,
    source: Path,
    group_input: Path,
    design_mat: Path,
    design_con: Path,
    roi_values: Path,
    condition_values: Path | None,
    project_root: Path,
    threshold: float,
) -> None:
    payload = {
        "Description": "FSL randomise covariate model FWE-corrected 1-p statistical map",
        "TaskName": task,
        "ModelLabel": row["model_label"],
        "Covariates": row["covariates"].split(",") if row["covariates"] else [],
        "Analysis": row["analysis"],
        "Network": row["network"],
        "Component": row["component"],
        "MapType": row["map_type"],
        "ConditionContrast": row["condition_contrast"],
        "DesignContrast": row["design_contrast"],
        "ContrastName": row["contrast_name"],
        "ContrastVector": row["contrast_vector"].split(" "),
        "TestedCovariate": row["tested_covariate"],
        "InferenceMethod": row["inference"],
        "PeakOneMinusP": float(row["peak_corrp"]),
        "SignificanceThresholdOneMinusP": threshold,
        "Sources": [relative_path(source, project_root)],
        "GroupInput": relative_path(group_input, project_root),
        "DesignMatrix": relative_path(design_mat, project_root),
        "DesignContrasts": relative_path(design_con, project_root),
        "ROIValues": relative_path(roi_values, project_root),
        "GeneratedBy": [{"Name": "FSL randomise"}],
    }
    if condition_values is not None:
        payload["ConditionValues"] = relative_path(condition_values, project_root)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def read_job_manifests(fsl_dir: Path, models: list[str]) -> list[Path]:
    manifests: list[Path] = []
    for model in models:
        manifests.extend(sorted(fsl_dir.glob(f"**/covariate-models/model-{model}/randomise_jobs.tsv")))
    return manifests


def main() -> int:
    args = parse_args()
    if not 0.0 <= args.threshold <= 1.0:
        raise ValueError("--threshold must be between 0 and 1.")
    project_root = Path(__file__).resolve().parents[1]
    fsl_dir = args.fsl_dir.resolve()
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir
        else fsl_dir / "covariate_randomise_summary"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    models = normalize_models(args.models)
    manifests = read_job_manifests(fsl_dir, models)
    if not manifests:
        raise ValueError(f"No covariate randomise manifests found under {fsl_dir}")

    methods = [CLUSTER_METHOD]
    if args.include_tfce:
        methods.append(TFCE_METHOD)

    fslstats = shutil.which("fslstats")
    fslnvols = shutil.which("fslnvols")
    fslmaths = shutil.which("fslmaths")
    fslroi = shutil.which("fslroi")
    required_commands = {"fslstats": fslstats, "fslnvols": fslnvols}
    if not args.no_copy:
        required_commands.update({"fslmaths": fslmaths, "fslroi": fslroi})
    missing_commands = [name for name, path in required_commands.items() if path is None]
    if missing_commands:
        raise RuntimeError(f"Required FSL commands are not on PATH: {missing_commands}")
    assert fslstats is not None and fslnvols is not None

    rows: list[dict[str, str]] = []
    missing_paths: set[Path] = set()
    errors: list[str] = []
    copied_count = 0
    roi_values_count = 0
    roi_value_rows = 0
    condition_values_count = 0
    condition_value_rows = 0
    significant_count = 0
    jobs_checked = 0

    for manifest in manifests:
        model_dir = manifest.parent
        model_label = model_dir.name.removeprefix("model-")
        component_dir = model_dir.parent.parent
        dr_dir = component_dir.parent.parent
        analysis, component, map_type = parse_component_dir(component_dir)
        for job in read_tsv(manifest):
            jobs_checked += 1
            contrast = job["contrast"]
            network = job["network"]
            group_input = Path(job["group_input"])
            design_mat = Path(job["design_mat"])
            design_con = Path(job["design_con"])
            output_prefix = Path(job["output_prefix"])
            contrast_dir = group_input.parent
            audit_path = contrast_dir / "covariate_audit.tsv"
            marker = Path(f"{output_prefix}.complete")

            audit_rows: list[dict[str, str]] = []
            covariates: list[str] = covariates_from_audit(audit_path)
            expected_participants: int | None = None
            if audit_path.is_file():
                try:
                    audit_rows = read_audit(audit_path)
                    expected_participants = len(audit_rows)
                except (OSError, ValueError) as error:
                    errors.append(str(error))
            else:
                missing_paths.add(audit_path)

            design_valid, design_contrasts, _num_waves = parse_design_con(design_con)
            if not design_valid:
                missing_paths.add(design_con)
            if not design_mat.is_file():
                missing_paths.add(design_mat)
            group_exists = group_input.is_file()
            group_volumes: int | None = None
            group_complete = False
            if group_exists and expected_participants is not None:
                try:
                    group_volumes = volume_count(group_input, fslnvols)
                    group_complete = group_volumes == expected_participants
                    if not group_complete:
                        errors.append(
                            f"{group_input}: {group_volumes} volumes; expected {expected_participants}"
                        )
                except (OSError, subprocess.CalledProcessError, ValueError) as error:
                    errors.append(f"{group_input}: {error}")
            elif not group_exists:
                missing_paths.add(group_input)

            for design_contrast in design_contrasts:
                number = int(design_contrast["number"])
                contrast_name = str(design_contrast["name"])
                vector = [str(value) for value in design_contrast["vector"]]
                direction, tested_covariate = vector_label(vector, covariates)
                tstat = Path(f"{output_prefix}_tstat{number}.nii.gz")
                for method, suffix in methods:
                    corrp = Path(f"{output_prefix}_{suffix}_tstat{number}.nii.gz")
                    corrp_exists = corrp.is_file()
                    tstat_exists = tstat.is_file()
                    if not tstat_exists:
                        missing_paths.add(tstat)
                    if not corrp_exists:
                        missing_paths.add(corrp)
                    status = "ok"
                    peak: float | None = None
                    if not design_valid:
                        status = "invalid_design_con"
                    elif not group_complete:
                        status = "invalid_group_input"
                    elif not marker.is_file():
                        status = "missing_completion_marker"
                    elif not tstat_exists:
                        status = "missing_tstat"
                    elif not corrp_exists:
                        status = "missing_corrp"
                    else:
                        try:
                            peak = peak_value(corrp, fslstats)
                        except (OSError, subprocess.CalledProcessError, ValueError) as error:
                            status = "peak_error"
                            errors.append(f"{corrp}: {error}")

                    significant = peak is not None and peak > args.threshold
                    significant_count += int(significant)
                    row = {
                        "model_label": model_label,
                        "covariates": ",".join(covariates),
                        "analysis": analysis,
                        "network": network,
                        "component": component,
                        "map_type": map_type,
                        "condition_contrast": contrast,
                        "design_contrast": f"C{number}",
                        "contrast_name": contrast_name,
                        "direction": direction,
                        "tested_covariate": tested_covariate,
                        "contrast_vector": " ".join(vector),
                        "inference": method,
                        "design_con_valid": str(design_valid).lower(),
                        "group_input_exists": str(group_exists).lower(),
                        "expected_participants": "n/a" if expected_participants is None else str(expected_participants),
                        "group_input_volumes": "n/a" if group_volumes is None else str(group_volumes),
                        "group_input_complete": str(group_complete).lower(),
                        "completion_marker_exists": str(marker.is_file()).lower(),
                        "tstat_exists": str(tstat_exists).lower(),
                        "corrp_exists": str(corrp_exists).lower(),
                        "peak_corrp": "n/a" if peak is None else f"{peak:.8g}",
                        "peak_gt_threshold": str(significant).lower(),
                        "status": status,
                        "group_input": relative_path(group_input, project_root),
                        "design_mat": relative_path(design_mat, project_root),
                        "design_con": relative_path(design_con, project_root),
                        "corrp_file": relative_path(corrp, project_root),
                        "copied_image": "",
                        "copied_sidecar": "",
                        "roi_values_tsv": "",
                        "condition_values_tsv": "",
                    }

                    if significant and status == "ok" and not args.no_copy:
                        destination = output_dir / copied_name(
                            args.task,
                            args.space,
                            analysis,
                            model_label,
                            network,
                            component,
                            contrast,
                            contrast_name,
                            method,
                        )
                        sidecar = destination.with_name(destination.name.removesuffix(".nii.gz") + ".json")
                        roi_values = output_dir / roi_values_name(destination)
                        condition_values = (
                            output_dir / condition_values_name(destination)
                            if tested_covariate == "intercept"
                            else None
                        )
                        shutil.copy2(corrp, destination)
                        row["copied_image"] = relative_path(destination, project_root)
                        row["copied_sidecar"] = relative_path(sidecar, project_root)
                        row["roi_values_tsv"] = relative_path(roi_values, project_root)
                        if condition_values is not None:
                            row["condition_values_tsv"] = relative_path(condition_values, project_root)
                        try:
                            assert fslmaths is not None and fslroi is not None
                            metadata = {
                                "model_label": model_label,
                                "analysis": analysis,
                                "network": network,
                                "component": component,
                                "map_type": map_type,
                                "condition_contrast": contrast,
                                "design_contrast": f"C{number}",
                                "contrast_name": contrast_name,
                                "direction": direction,
                                "tested_covariate": tested_covariate,
                            }
                            extracted = extract_roi_values(
                                corrp,
                                args.threshold,
                                group_input,
                                audit_rows,
                                roi_values,
                                metadata,
                                str(fslmaths),
                                str(fslroi),
                                fslstats,
                            )
                            condition_rows = 0
                            if condition_values is not None:
                                condition_rows = extract_condition_values(
                                    corrp,
                                    args.threshold,
                                    dr_dir,
                                    int(component),
                                    map_type,
                                    audit_rows,
                                    condition_values,
                                    metadata,
                                    str(fslmaths),
                                    str(fslroi),
                                    fslstats,
                                )
                            write_sidecar(
                                sidecar,
                                row,
                                args.task,
                                corrp,
                                group_input,
                                design_mat,
                                design_con,
                                roi_values,
                                condition_values,
                                project_root,
                                args.threshold,
                            )
                            copied_count += 1
                            roi_values_count += 1
                            roi_value_rows += extracted
                            if condition_values is not None:
                                condition_values_count += 1
                                condition_value_rows += condition_rows
                        except (OSError, subprocess.CalledProcessError, ValueError) as error:
                            row["status"] = "roi_export_error"
                            row["roi_values_tsv"] = ""
                            row["condition_values_tsv"] = ""
                            roi_values.unlink(missing_ok=True)
                            if condition_values is not None:
                                condition_values.unlink(missing_ok=True)
                            sidecar.unlink(missing_ok=True)
                            errors.append(f"{corrp}: {error}")
                    rows.append(row)

    output_tsv = output_dir / f"task-{args.task}_covariate-randomise_peak_summary.tsv"
    write_tsv(output_tsv, rows, list(SUMMARY_FIELDS))
    (output_dir / "README.md").write_text(
        "# Covariate Randomise Summary\n\n"
        "Generated by `code/check_covariate_randomise_results.py`. FSL corrected-p "
        "images store `1-p`; values greater than 0.95 correspond to corrected "
        "p-values below 0.05. The summary includes C1/C2 mean-effect tests and "
        "C3/C4 covariate-effect tests from the four-row covariate `design.con` "
        "files. Significant maps are copied here with JSON sidecars and ROI-value "
        "TSVs that join subject-level contrast betas to the covariate audit table. "
        "For significant C1/C2 intercept tests, a second stage-2 beta timeseries "
        "TSV is written for four-condition bar plots.\n"
    )

    expected_rows = jobs_checked * 4 * len(methods)
    print(f"Model manifests: {len(manifests)}")
    print(f"Randomise jobs checked: {jobs_checked}")
    print(f"Summary rows: {len(rows)}/{expected_rows}")
    print(f"Significant maps with peak > {args.threshold:g}: {significant_count}")
    print(f"Significant maps copied: {copied_count}/{significant_count}")
    print(f"ROI-value TSVs written: {roi_values_count} ({roi_value_rows} rows)")
    print(
        f"Condition-value TSVs written: {condition_values_count} "
        f"({condition_value_rows} rows)"
    )
    print(f"Missing or invalid required paths: {len(missing_paths)}")
    print(f"Errors: {len(errors)}")
    print(f"Wrote {output_tsv}")
    for path in sorted(missing_paths, key=str)[:20]:
        print(f"MISSING: {path}", file=sys.stderr)
    if len(missing_paths) > 20:
        print(f"... and {len(missing_paths) - 20} more missing paths", file=sys.stderr)
    for error in errors[:20]:
        print(f"ERROR: {error}", file=sys.stderr)
    incomplete = bool(missing_paths or errors or len(rows) != expected_rows)
    return 1 if args.fail_on_missing and incomplete else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
