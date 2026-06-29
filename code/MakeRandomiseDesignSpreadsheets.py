#!/usr/bin/env python3
"""Write labeled randomise design spreadsheets for FSL GUI entry."""

from __future__ import annotations

import argparse
import csv
import math
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
COVARIATE_ALIASES = {
    "fdmean": "delta_fd_mean",
    "fd_mean": "delta_fd_mean",
    "delta_fd_mean": "delta_fd_mean",
    "tsnr": "delta_tsnr",
    "delta_tsnr": "delta_tsnr",
    "pupil": "delta_mean_pupil_area",
    "mean_pupil_area": "delta_mean_pupil_area",
    "delta_mean_pupil_area": "delta_mean_pupil_area",
    "blink": "delta_blink_rate_per_min",
    "blinks": "delta_blink_rate_per_min",
    "blink_rate": "delta_blink_rate_per_min",
    "blink_rate_per_min": "delta_blink_rate_per_min",
    "delta_blink_rate_per_min": "delta_blink_rate_per_min",
    "eye_closed": "delta_eye_closed_fraction",
    "eye_closed_fraction": "delta_eye_closed_fraction",
    "delta_eye_closed_fraction": "delta_eye_closed_fraction",
}


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def write_table(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    delimiter = "," if suffix == ".csv" else "\t"
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=fieldnames, delimiter=delimiter, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def parse_covariates(value: str) -> list[str]:
    covariates: list[str] = []
    for item in value.split(","):
        raw = item.strip()
        if raw == "":
            continue
        covariate = COVARIATE_ALIASES.get(raw, raw)
        if covariate in covariates:
            raise ValueError(f"Duplicate covariate: {raw}")
        covariates.append(covariate)
    if not covariates:
        raise ValueError("At least one covariate is required")
    return covariates


def parse_contrasts(value: str) -> list[str]:
    if value.strip().lower() == "all":
        return list(CONTRASTS)
    contrasts: list[str] = []
    for item in value.split(","):
        contrast = item.strip()
        if contrast == "":
            continue
        if contrast not in CONTRASTS:
            raise ValueError(f"Unknown contrast: {contrast}")
        if contrast in contrasts:
            raise ValueError(f"Duplicate contrast: {contrast}")
        contrasts.append(contrast)
    if not contrasts:
        raise ValueError("At least one contrast is required")
    return contrasts


def parse_float(value: str, label: str) -> float:
    try:
        number = float(value)
    except ValueError as error:
        raise ValueError(f"{label} is not numeric: {value}") from error
    if not math.isfinite(number):
        raise ValueError(f"{label} is not finite: {value}")
    return number


def read_subject_order(path: Path) -> list[str]:
    rows = read_tsv(path)
    if not rows:
        raise ValueError(f"{path} has no rows")
    required = {"randomise_index", "participant"}
    missing = required.difference(rows[0])
    if missing:
        raise ValueError(f"{path} is missing columns: {sorted(missing)}")
    ordered = sorted(rows, key=lambda row: int(row["randomise_index"]))
    participants = [row["participant"] for row in ordered]
    if len(participants) != len(set(participants)):
        raise ValueError(f"{path} contains duplicate participants")
    return participants


def load_covariate_rows(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    rows = read_tsv(path)
    if not rows:
        raise ValueError(f"{path} has no rows")
    required = {"participant", "contrast", "complete"}
    missing = required.difference(rows[0])
    if missing:
        raise ValueError(f"{path} is missing columns: {sorted(missing)}")
    output: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        key = (row["participant"], row["contrast"])
        if key in output:
            raise ValueError(f"Duplicate row for {key[0]} {key[1]}")
        output[key] = row
    return output


def complete_participants(
    rows: dict[tuple[str, str], dict[str, str]], contrasts: list[str]
) -> list[str]:
    participants = sorted({participant for participant, _contrast in rows})
    complete: list[str] = []
    for participant in participants:
        if all(
            rows.get((participant, contrast), {}).get("complete", "").lower() == "true"
            for contrast in contrasts
        ):
            complete.append(participant)
    if not complete:
        raise ValueError("No participants have complete covariates for all requested contrasts")
    return complete


def build_design_rows(
    covariate_rows: dict[tuple[str, str], dict[str, str]],
    contrast: str,
    participants: list[str],
    covariates: list[str],
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    raw_values: dict[str, list[float]] = {covariate: [] for covariate in covariates}
    raw_by_participant: dict[str, dict[str, float]] = {}
    for participant in participants:
        row = covariate_rows.get((participant, contrast))
        if row is None:
            raise ValueError(f"Missing covariate row for {participant} {contrast}")
        if row["complete"].lower() != "true":
            raise ValueError(f"Incomplete covariate row for {participant} {contrast}")
        raw_by_participant[participant] = {}
        for covariate in covariates:
            if covariate not in row:
                raise ValueError(f"Missing covariate column: {covariate}")
            value = parse_float(row[covariate], f"{participant} {contrast} {covariate}")
            raw_by_participant[participant][covariate] = value
            raw_values[covariate].append(value)

    means = {
        covariate: sum(values) / len(values)
        for covariate, values in raw_values.items()
    }
    for covariate, values in raw_values.items():
        centered = [value - means[covariate] for value in values]
        if max(abs(value) for value in centered) < 1e-12:
            raise ValueError(f"{contrast}: {covariate} has zero variance after demeaning")

    matrix_rows: list[dict[str, str]] = []
    audit_rows: list[dict[str, str]] = []
    for index, participant in enumerate(participants):
        matrix_row = {
            "randomise_index": str(index),
            "participant": participant,
            "EV1_intercept": "1",
        }
        audit_row = {
            "randomise_index": str(index),
            "participant": participant,
            "contrast": contrast,
        }
        for ev_index, covariate in enumerate(covariates, start=2):
            raw = raw_by_participant[participant][covariate]
            demeaned = raw - means[covariate]
            matrix_row[f"EV{ev_index}_{covariate}_demeaned"] = f"{demeaned:.10g}"
            audit_row[covariate] = f"{raw:.10g}"
            audit_row[f"{covariate}_mean"] = f"{means[covariate]:.10g}"
            audit_row[f"{covariate}_demeaned"] = f"{demeaned:.10g}"
        matrix_rows.append(matrix_row)
        audit_rows.append(audit_row)
    return matrix_rows, audit_rows


def write_contrast_reference(output_dir: Path, covariates: list[str]) -> Path:
    ev_names = ["EV1_intercept"] + [
        f"EV{index}_{covariate}_demeaned"
        for index, covariate in enumerate(covariates, start=2)
    ]
    rows = [
        {
            "design_contrast": "C1",
            "direction": "positive",
            **{ev: ("1" if ev == "EV1_intercept" else "0") for ev in ev_names},
        },
        {
            "design_contrast": "C2",
            "direction": "negative",
            **{ev: ("-1" if ev == "EV1_intercept" else "0") for ev in ev_names},
        },
    ]
    path = output_dir / "task-rest_design-contrast-reference.tsv"
    write_table(path, rows, ["design_contrast", "direction", *ev_names])
    return path


def write_group_reference(output_dir: Path, participants: list[str]) -> Path:
    rows = [
        {"randomise_index": str(index), "participant": participant, "group": "1"}
        for index, participant in enumerate(participants)
    ]
    path = output_dir / "task-rest_design-group-reference.tsv"
    write_table(path, rows, ["randomise_index", "participant", "group"])
    return path


def write_readme(
    output_dir: Path,
    covariates: list[str],
    order_source: str,
    n_participants: int,
) -> Path:
    ev_columns = ["EV1_intercept"] + [
        f"EV{index}_{covariate}_demeaned"
        for index, covariate in enumerate(covariates, start=2)
    ]
    path = output_dir / "README.md"
    path.write_text(
        "# Randomise Design Spreadsheets\n\n"
        "These tables are for building FSL `design.mat`, `design.con`, and "
        "`design.grp` files in the FSL GLM GUI.\n\n"
        f"- Order source: `{order_source}`\n"
        f"- Participants: {n_participants}\n"
        f"- EV columns to paste into the design matrix: `{', '.join(ev_columns)}`\n"
        "- Use the `_demeaned` covariate columns in the design matrix. Raw "
        "columns in the audit files are for checking only.\n"
        "- Use `task-rest_design-contrast-reference.tsv` for the two contrasts: "
        "C1 tests the positive mean effect and C2 tests the negative mean effect.\n"
        "- Use `task-rest_design-group-reference.tsv` for the exchangeability "
        "groups; all rows are group 1 for this one-sample model.\n"
    )
    return path


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    qc_dir = repo_root / "derivatives" / "qc"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--group-covariates",
        type=Path,
        default=qc_dir / "task-rest_group_covariates.tsv",
    )
    parser.add_argument(
        "--subject-order",
        type=Path,
        help="subject_order.tsv from the exact randomise component directory.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=qc_dir / "randomise_design_spreadsheets",
    )
    parser.add_argument(
        "--covariates",
        default="fdmean",
        help="Comma-separated aliases or columns; default: fdmean.",
    )
    parser.add_argument("--contrasts", default="all")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    covariates = parse_covariates(args.covariates)
    contrasts = parse_contrasts(args.contrasts)
    covariate_rows = load_covariate_rows(args.group_covariates.resolve())
    if args.subject_order:
        participants = read_subject_order(args.subject_order.resolve())
        order_source = str(args.subject_order.resolve())
    else:
        participants = complete_participants(covariate_rows, contrasts)
        order_source = "sorted participants complete for all requested contrasts"

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_rows: list[dict[str, str]] = []
    for contrast in contrasts:
        matrix_rows, audit_rows = build_design_rows(
            covariate_rows, contrast, participants, covariates
        )
        matrix_fields = list(matrix_rows[0])
        audit_fields = list(audit_rows[0])
        matrix_tsv = output_dir / f"task-rest_contrast-{contrast}_design-matrix.tsv"
        matrix_csv = matrix_tsv.with_suffix(".csv")
        audit_tsv = output_dir / f"task-rest_contrast-{contrast}_covariate-audit.tsv"
        write_table(matrix_tsv, matrix_rows, matrix_fields)
        write_table(matrix_csv, matrix_rows, matrix_fields)
        write_table(audit_tsv, audit_rows, audit_fields)
        manifest_rows.append(
            {
                "contrast": contrast,
                "n_participants": str(len(participants)),
                "design_matrix_tsv": str(matrix_tsv),
                "design_matrix_csv": str(matrix_csv),
                "covariate_audit_tsv": str(audit_tsv),
                "ev_columns": ",".join(matrix_fields[2:]),
            }
        )

    contrast_reference = write_contrast_reference(output_dir, covariates)
    group_reference = write_group_reference(output_dir, participants)
    readme = write_readme(output_dir, covariates, order_source, len(participants))
    manifest = output_dir / "task-rest_design-spreadsheet_manifest.tsv"
    write_table(
        manifest,
        manifest_rows,
        [
            "contrast",
            "n_participants",
            "design_matrix_tsv",
            "design_matrix_csv",
            "covariate_audit_tsv",
            "ev_columns",
        ],
    )

    print(f"Participants: {len(participants)}")
    print(f"Covariates: {','.join(covariates)}")
    print(f"Contrasts: {len(contrasts)}")
    print(f"Order source: {order_source}")
    print(f"Wrote {manifest}")
    print(f"Wrote {contrast_reference}")
    print(f"Wrote {group_reference}")
    print(f"Wrote {readme}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"ERROR: {error}")
        raise SystemExit(1)
