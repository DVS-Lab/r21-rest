#!/usr/bin/env python3
"""Audit covariate randomise design matrices, masks, and input ordering."""

from __future__ import annotations

import argparse
import csv
import math
import re
import shutil
import subprocess
import sys
from pathlib import Path


FIELDS = (
    "model_label",
    "analysis",
    "network",
    "component",
    "map_type",
    "condition_contrast",
    "covariates",
    "n_participants",
    "num_waves",
    "num_points",
    "group_input_volumes",
    "group_input_complete",
    "mask_exists",
    "mask_voxels",
    "mask_volume_mm3",
    "design_con_valid",
    "intercept_all_ones",
    "covariate_columns_demeaned",
    "design_matches_covariate_audit",
    "max_abs_design_audit_delta",
    "subject_order_matches_audit",
    "image_list_matches_audit",
    "c3_c4_test_last_covariate",
    "complete",
    "notes",
)


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]
    derivatives = project_root / "derivatives"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", default="fdmean-blink,fdmean-pupil")
    parser.add_argument("--fsl-dir", type=Path, default=derivatives / "fsl")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Tracked summary directory (default: derivatives/fsl/covariate_randomise_summary).",
    )
    parser.add_argument("--task", default="rest")
    parser.add_argument("--tolerance", type=float, default=1e-6)
    parser.add_argument("--fail-on-error", action="store_true")
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
        raise ValueError("No models requested")
    return models


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(FIELDS), delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def parse_component_dir(path: Path) -> tuple[str, str, str]:
    match = re.fullmatch(r"component-(\d+)_stat-([A-Za-z0-9]+)", path.name)
    if not match:
        raise ValueError(f"Cannot parse component directory: {path}")
    dr_dir = path.parent.parent
    analysis = dr_dir.name.removeprefix("dual-regression_").removesuffix(".dr")
    return analysis, match.group(1), match.group(2)


def parse_design_matrix(path: Path) -> tuple[int, int, list[list[float]]]:
    lines = [line.strip() for line in path.read_text().splitlines()]
    num_waves: int | None = None
    num_points: int | None = None
    matrix_start: int | None = None
    for index, line in enumerate(lines):
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "/NumWaves" and len(parts) > 1:
            num_waves = int(parts[1])
        elif parts[0] == "/NumPoints" and len(parts) > 1:
            num_points = int(parts[1])
        elif parts[0] == "/Matrix":
            matrix_start = index + 1
            break
    if num_waves is None or num_points is None or matrix_start is None:
        raise ValueError(f"Invalid FSL design matrix: {path}")
    matrix = [
        [float(value) for value in line.split()]
        for line in lines[matrix_start:]
        if line
    ]
    if len(matrix) != num_points or any(len(row) != num_waves for row in matrix):
        raise ValueError(f"Design matrix dimensions do not match headers: {path}")
    return num_waves, num_points, matrix


def parse_design_con(path: Path, num_waves: int) -> tuple[bool, bool]:
    lines = [line.strip() for line in path.read_text().splitlines()]
    try:
        matrix_start = lines.index("/Matrix") + 1
    except ValueError:
        return False, False
    matrix = [line.split() for line in lines[matrix_start:] if line]
    expected = [
        ["1", *["0"] * (num_waves - 1)],
        ["-1", *["0"] * (num_waves - 1)],
        [*["0"] * (num_waves - 1), "1"],
        [*["0"] * (num_waves - 1), "-1"],
    ]
    return len(matrix) == 4 and all(len(row) == num_waves for row in matrix), matrix == expected


def audit_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    rows = sorted(read_tsv(path), key=lambda row: int(row["randomise_index"]))
    fields = rows[0].keys() if rows else []
    covariates = [
        field
        for field in fields
        if field not in {"randomise_index", "participant"}
        and not field.endswith("_demeaned")
    ]
    return rows, covariates


def participant_order(rows: list[dict[str, str]]) -> list[str]:
    return [row["participant"] for row in rows]


def read_subject_order(path: Path) -> list[str]:
    return participant_order(sorted(read_tsv(path), key=lambda row: int(row["randomise_index"])))


def image_list_participants(path: Path) -> list[str]:
    participants: list[str] = []
    for line in path.read_text().splitlines():
        match = re.search(r"sub-[A-Za-z0-9]+", line)
        participants.append(match.group(0) if match else "")
    return participants


def fslnvols(path: Path, command: str) -> int:
    result = subprocess.run([command, str(path)], text=True, capture_output=True, check=True)
    return int(result.stdout.strip())


def mask_volume(path: Path, command: str) -> tuple[str, str]:
    result = subprocess.run([command, str(path), "-V"], text=True, capture_output=True, check=True)
    values = result.stdout.split()
    if len(values) < 2:
        raise ValueError(f"Unexpected fslstats -V output for {path}: {result.stdout!r}")
    return values[0], values[1]


def bool_text(value: bool) -> str:
    return str(value).lower()


def main() -> int:
    args = parse_args()
    if args.tolerance <= 0:
        raise ValueError("--tolerance must be positive")
    fsl_dir = args.fsl_dir.resolve()
    output_dir = args.output_dir.resolve() if args.output_dir else fsl_dir / "covariate_randomise_summary"
    models = normalize_models(args.models)
    manifests: list[Path] = []
    for model in models:
        manifests.extend(sorted(fsl_dir.glob(f"**/covariate-models/model-{model}/randomise_jobs.tsv")))
    if not manifests:
        raise ValueError(f"No covariate randomise manifests found under {fsl_dir}")

    fslnvols_command = shutil.which("fslnvols")
    fslstats_command = shutil.which("fslstats")
    if fslnvols_command is None or fslstats_command is None:
        raise RuntimeError("Required FSL commands are not on PATH: fslnvols, fslstats")

    rows: list[dict[str, str]] = []
    for manifest in manifests:
        model_dir = manifest.parent
        model_label = model_dir.name.removeprefix("model-")
        component_dir = model_dir.parent.parent
        dr_dir = component_dir.parent.parent
        analysis, component, map_type = parse_component_dir(component_dir)
        mask = dr_dir / "mask.nii.gz"
        mask_voxels = "n/a"
        mask_mm3 = "n/a"
        mask_exists = mask.is_file()
        notes: list[str] = []
        if mask_exists:
            try:
                mask_voxels, mask_mm3 = mask_volume(mask, fslstats_command)
            except (OSError, subprocess.CalledProcessError, ValueError) as error:
                notes.append(f"mask_volume_error:{error}")
        else:
            notes.append("missing_mask")

        for job in read_tsv(manifest):
            contrast_dir = Path(job["group_input"]).parent
            audit_path = contrast_dir / "covariate_audit.tsv"
            subject_order = contrast_dir / "subject_order.tsv"
            image_list = contrast_dir / "image_list.txt"
            design_mat = Path(job["design_mat"])
            design_con = Path(job["design_con"])
            group_input = Path(job["group_input"])
            row_notes = list(notes)

            audit, covariates = audit_rows(audit_path)
            participants = participant_order(audit)
            n_participants = len(participants)
            num_waves, num_points, matrix = parse_design_matrix(design_mat)
            design_con_shape_valid, c3_c4_last = parse_design_con(design_con, num_waves)
            group_volumes = fslnvols(group_input, fslnvols_command)

            intercept_all_ones = all(abs(design_row[0] - 1.0) <= args.tolerance for design_row in matrix)
            covariate_columns_demeaned = all(
                abs(sum(design_row[column] for design_row in matrix)) <= args.tolerance
                for column in range(1, num_waves)
            )
            max_delta = 0.0
            design_matches_audit = True
            for row_index, audit_row in enumerate(audit):
                for column, covariate in enumerate(covariates, start=1):
                    expected = float(audit_row[f"{covariate}_demeaned"])
                    observed = matrix[row_index][column]
                    delta = abs(observed - expected)
                    max_delta = max(max_delta, delta)
                    if delta > args.tolerance:
                        design_matches_audit = False
            subject_order_matches = subject_order.is_file() and read_subject_order(subject_order) == participants
            image_list_matches = image_list.is_file() and image_list_participants(image_list) == participants
            group_complete = group_volumes == n_participants

            checks = {
                "group_input_complete": group_complete,
                "mask_exists": mask_exists,
                "design_con_valid": design_con_shape_valid,
                "intercept_all_ones": intercept_all_ones,
                "covariate_columns_demeaned": covariate_columns_demeaned,
                "design_matches_covariate_audit": design_matches_audit,
                "subject_order_matches_audit": subject_order_matches,
                "image_list_matches_audit": image_list_matches,
                "c3_c4_test_last_covariate": c3_c4_last,
            }
            for name, passed in checks.items():
                if not passed:
                    row_notes.append(name)
            complete = all(checks.values()) and num_points == n_participants and num_waves == 1 + len(covariates)
            if num_points != n_participants:
                row_notes.append("num_points_mismatch")
            if num_waves != 1 + len(covariates):
                row_notes.append("num_waves_mismatch")

            rows.append(
                {
                    "model_label": model_label,
                    "analysis": analysis,
                    "network": job["network"],
                    "component": component,
                    "map_type": map_type,
                    "condition_contrast": job["contrast"],
                    "covariates": ",".join(covariates),
                    "n_participants": str(n_participants),
                    "num_waves": str(num_waves),
                    "num_points": str(num_points),
                    "group_input_volumes": str(group_volumes),
                    "group_input_complete": bool_text(group_complete),
                    "mask_exists": bool_text(mask_exists),
                    "mask_voxels": mask_voxels,
                    "mask_volume_mm3": mask_mm3,
                    "design_con_valid": bool_text(design_con_shape_valid),
                    "intercept_all_ones": bool_text(intercept_all_ones),
                    "covariate_columns_demeaned": bool_text(covariate_columns_demeaned),
                    "design_matches_covariate_audit": bool_text(design_matches_audit),
                    "max_abs_design_audit_delta": f"{max_delta:.8g}",
                    "subject_order_matches_audit": bool_text(subject_order_matches),
                    "image_list_matches_audit": bool_text(image_list_matches),
                    "c3_c4_test_last_covariate": bool_text(c3_c4_last),
                    "complete": bool_text(complete),
                    "notes": ",".join(row_notes),
                }
            )

    output = output_dir / f"task-{args.task}_covariate-randomise_integrity.tsv"
    write_tsv(output, rows)
    complete_count = sum(row["complete"] == "true" for row in rows)
    mask_voxel_values = [
        int(row["mask_voxels"])
        for row in rows
        if row["mask_voxels"].isdigit()
    ]
    print(f"Model manifests: {len(manifests)}")
    print(f"Randomise jobs audited: {len(rows)}")
    print(f"Complete integrity rows: {complete_count}/{len(rows)}")
    if mask_voxel_values:
        print(f"Mask voxel range: {min(mask_voxel_values)}-{max(mask_voxel_values)}")
    print(f"Wrote {output}")
    if args.fail_on_error and complete_count != len(rows):
        for row in rows:
            if row["complete"] != "true":
                print(
                    f"ERROR: {row['model_label']} {row['analysis']} {row['component']} "
                    f"{row['condition_contrast']}: {row['notes']}",
                    file=sys.stderr,
                )
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)
