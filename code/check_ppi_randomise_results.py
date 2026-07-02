#!/usr/bin/env python3
"""Compile Smith09 DMN x ECN interaction randomise outputs."""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

from check_randomise_results import (
    CLUSTER_METHOD,
    CONTRASTS,
    DIRECTIONS,
    TFCE_METHOD,
    extract_roi_values,
    peak_value,
    relative_path,
    subject_count,
    verify_design_con,
    volume_count,
)


SUMMARY_FIELDS = (
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


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]
    fsl_dir = project_root / "derivatives" / "fsl"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", default="rest")
    parser.add_argument("--space", default="MNI152NLin6Asym")
    parser.add_argument("--component", type=int, default=11)
    parser.add_argument("--map-type", choices=("beta", "z"), default="beta")
    parser.add_argument("--threshold", type=float, default=0.95)
    parser.add_argument("--cluster-threshold", type=float, default=3.1)
    parser.add_argument("--include-tfce", action="store_true")
    parser.add_argument("--no-copy", action="store_true")
    parser.add_argument(
        "--ppi-dir",
        type=Path,
        default=fsl_dir / "dual-regression_smith09_denoised_ppi-dmn-ecn.dr",
        help="Completed DMN x ECN interaction dual-regression-like directory.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=fsl_dir / "ppi_randomise_summary",
        help="Tracked output directory for compact summaries and copied maps.",
    )
    parser.add_argument(
        "--fail-on-missing",
        action="store_true",
        help="Exit nonzero when expected outputs are missing or invalid.",
    )
    return parser.parse_args()


def write_tsv(path: Path, rows: list[dict[str, str]], fields: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def camel_label(value: str) -> str:
    pieces = [piece for piece in value.replace("_", "-").split("-") if piece]
    return "".join(piece[:1].upper() + piece[1:] for piece in pieces)


def copied_name(
    task: str,
    space: str,
    component: int,
    contrast: str,
    direction: str,
    method: str,
) -> str:
    description = (
        f"Smith09DmnEcnPpiComp{component:04d}"
        f"{camel_label(contrast)}{camel_label(direction)}{camel_label(method)}Corrp"
    )
    return f"task-{task}_space-{space}_desc-{description}_stat-corrp_statmap.nii.gz"


def roi_values_name(copied_image: Path) -> str:
    stem = copied_image.name.removesuffix("_stat-corrp_statmap.nii.gz")
    return f"{stem}_stat-stage2Beta_timeseries.tsv"


def write_sidecar(
    path: Path,
    source: Path,
    project_root: Path,
    row: dict[str, str],
    task: str,
    threshold: float,
    cluster_threshold: float,
    roi_values: Path,
) -> None:
    payload = {
        "Description": "FSL randomise FWE-corrected 1-p map for Smith09 DMN x ECN interaction stage-2 maps",
        "TaskName": task,
        "Analysis": row["analysis"],
        "Network": row["network"],
        "Component": int(row["component"]),
        "ConditionContrast": row["condition_contrast"],
        "DesignContrast": row["design_contrast"],
        "Direction": row["direction"],
        "InferenceMethod": row["inference"],
        "PeakOneMinusP": float(row["peak_corrp"]),
        "SignificanceThresholdOneMinusP": threshold,
        "ClusterFormingTThreshold": cluster_threshold,
        "Sources": [relative_path(source, project_root)],
        "ROIValues": relative_path(roi_values, project_root),
        "GeneratedBy": [{"Name": "FSL randomise"}],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def main() -> int:
    args = parse_args()
    if not 0.0 <= args.threshold <= 1.0:
        raise ValueError("--threshold must be between 0 and 1.")
    if args.component < 1:
        raise ValueError("--component must be positive.")

    project_root = Path(__file__).resolve().parents[1]
    ppi_dir = args.ppi_dir.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    fslstats = shutil.which("fslstats")
    fslnvols = shutil.which("fslnvols")
    fslmaths = shutil.which("fslmaths")
    fslroi = shutil.which("fslroi")
    required = {"fslstats": fslstats, "fslnvols": fslnvols}
    if not args.no_copy:
        required.update({"fslmaths": fslmaths, "fslroi": fslroi})
    missing_commands = [name for name, path in required.items() if path is None]
    if missing_commands:
        raise RuntimeError(f"Required FSL commands are not on PATH: {missing_commands}")
    assert fslstats is not None and fslnvols is not None

    component_padded = f"{args.component:04d}"
    component_dir = ppi_dir / "contrasts" / f"component-{component_padded}_stat-{args.map_type}"
    design_valid = verify_design_con(component_dir / "design.con")
    subject_order = component_dir / "subject_order.tsv"
    expected_participants: int | None = None
    validation_errors: list[str] = []
    missing_paths: set[Path] = set()

    component_inputs_complete = design_valid
    if not design_valid:
        missing_paths.add(component_dir / "design.con")
    for name in ("design.mat", "design.grp"):
        path = component_dir / name
        if not path.is_file():
            missing_paths.add(path)
            component_inputs_complete = False
    if subject_order.is_file():
        try:
            expected_participants = subject_count(subject_order)
        except (OSError, ValueError) as error:
            validation_errors.append(str(error))
            component_inputs_complete = False
    else:
        missing_paths.add(subject_order)
        component_inputs_complete = False
    if not (ppi_dir / "mask.nii.gz").is_file():
        missing_paths.add(ppi_dir / "mask.nii.gz")
        component_inputs_complete = False

    methods = [CLUSTER_METHOD]
    if args.include_tfce:
        methods.append(TFCE_METHOD)

    rows: list[dict[str, str]] = []
    peak_errors: list[str] = []
    significant_count = 0
    copied_count = 0
    roi_value_count = 0
    roi_value_rows = 0
    tstat_count = 0
    corrp_count = 0
    network = "dmn-x-ecn"
    analysis = "smith09_ppi-dmn-ecn"

    for contrast in CONTRASTS:
        group_input = component_dir / contrast / (
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
                        f"{group_input}: {group_volumes} volumes; expected {expected_participants}"
                    )
            except (OSError, subprocess.CalledProcessError, ValueError) as error:
                validation_errors.append(f"{group_input}: {error}")

        prefix = component_dir / "randomise" / (
            f"task-{args.task}_component-{component_padded}_stat-{args.map_type}_contrast-{contrast}"
        )
        tstats = {
            number: Path(f"{prefix}_tstat{number}.nii.gz")
            for number, _direction in DIRECTIONS
        }
        for path in tstats.values():
            if path.is_file():
                tstat_count += 1
            else:
                missing_paths.add(path)

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
                row = {
                    "analysis": analysis,
                    "network": network,
                    "component": str(args.component),
                    "condition_contrast": contrast,
                    "design_contrast": f"C{number}",
                    "direction": direction,
                    "inference": method,
                    "design_con_valid": str(design_valid).lower(),
                    "group_input_exists": str(group_exists).lower(),
                    "expected_participants": "n/a" if expected_participants is None else str(expected_participants),
                    "group_input_volumes": "n/a" if group_volumes is None else str(group_volumes),
                    "group_input_complete": str(group_complete).lower(),
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
                    assert fslmaths is not None and fslroi is not None
                    destination = output_dir / copied_name(
                        args.task,
                        args.space,
                        args.component,
                        contrast,
                        direction,
                        method,
                    )
                    sidecar = destination.with_name(destination.name.removesuffix(".nii.gz") + ".json")
                    roi_values = output_dir / roi_values_name(destination)
                    shutil.copy2(corrp, destination)
                    row["copied_image"] = relative_path(destination, project_root)
                    row["copied_sidecar"] = relative_path(sidecar, project_root)
                    row["roi_values_tsv"] = relative_path(roi_values, project_root)
                    extracted_rows = extract_roi_values(
                        corrp,
                        args.threshold,
                        ppi_dir,
                        args.component,
                        args.map_type,
                        roi_values,
                        {
                            "sensitivity_label": "none",
                            "analysis": analysis,
                            "network": network,
                            "component": str(args.component),
                            "condition_contrast": contrast,
                            "direction": direction,
                        },
                        set(),
                        str(fslmaths),
                        str(fslroi),
                        str(fslstats),
                    )
                    write_sidecar(
                        sidecar,
                        corrp,
                        project_root,
                        row,
                        args.task,
                        args.threshold,
                        args.cluster_threshold,
                        roi_values,
                    )
                    copied_count += 1
                    roi_value_count += 1
                    roi_value_rows += extracted_rows
                rows.append(row)

    output_tsv = output_dir / f"task-{args.task}_ppi-dmn-ecn_randomise_peak_summary.tsv"
    write_tsv(output_tsv, rows, SUMMARY_FIELDS)
    readme = output_dir / "README.md"
    readme.write_text(
        "# PPI Randomise Summary\n\n"
        "Generated by `code/check_ppi_randomise_results.py`. This folder contains "
        "small, GitHub-tracked summaries for the Smith09 DMN x ECN interaction "
        "analysis created by `code/run_smith09_dmn_ecn_ppi.sh`. FSL corrected-p "
        "images store `1-p`, so values greater than 0.95 correspond to corrected "
        "p-values below 0.05. Significant corrected maps are copied here with JSON "
        "sidecars and small stage-2 beta TSVs for portable plotting.\n"
    )

    total_expected = len(CONTRASTS) * len(DIRECTIONS) * len(methods)
    print(f"PPI directory: {ppi_dir}")
    print(f"Design valid: {str(design_valid).lower()}")
    print(f"t-stat images present: {tstat_count}/{len(CONTRASTS) * len(DIRECTIONS)}")
    print(f"corrp images present: {corrp_count}/{total_expected}")
    print(f"Corrected maps with peak > {args.threshold}: {significant_count}")
    print(f"Copied maps: {copied_count}")
    print(f"ROI-value TSVs written: {roi_value_count} ({roi_value_rows} rows)")
    print(f"Wrote {output_tsv}")

    if peak_errors:
        print("Peak errors:", file=sys.stderr)
        for error in peak_errors:
            print(f"  {error}", file=sys.stderr)
    if validation_errors:
        print("Validation errors:", file=sys.stderr)
        for error in validation_errors:
            print(f"  {error}", file=sys.stderr)
    if missing_paths:
        print("Missing expected paths:", file=sys.stderr)
        for path in sorted(missing_paths)[:40]:
            print(f"  {path}", file=sys.stderr)
        if len(missing_paths) > 40:
            print(f"  ... {len(missing_paths) - 40} more", file=sys.stderr)

    if args.fail_on_missing and (missing_paths or validation_errors or peak_errors):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
