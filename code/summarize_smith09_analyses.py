#!/usr/bin/env python3
"""Combine Smith09 component matches from the four group-ICA analyses."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


ANALYSES = [
    ("smoothed", "automatic", "smith09_dim-00_task-rest"),
    ("smoothed", "20", "smith09_dim-20_task-rest"),
    ("denoised", "automatic", "smith09_denoised_dim-00_task-rest"),
    ("denoised", "20", "smith09_denoised_dim-20_task-rest"),
]


def read_analysis(
    fsl_dir: Path,
    data_set: str,
    dimension: str,
    directory: str,
) -> list[dict[str, str]]:
    analysis_dir = fsl_dir / directory
    best_path = analysis_dir / "smith09_best_matches.tsv"
    matrix_path = analysis_dir / "smith09_component_correlations.tsv"
    with best_path.open(newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter="\t"))
    with matrix_path.open(newline="") as stream:
        component_rows = sum(1 for _ in csv.DictReader(stream, delimiter="\t"))
    if len(rows) != 10:
        raise ValueError(f"{best_path}: expected 10 network rows; found {len(rows)}")

    output = []
    for row in rows:
        required = {
            "smith09_map",
            "network",
            "analysis_priority",
            "best_component",
            "correlation",
            "absolute_correlation",
            "sign",
            "next_component",
            "next_correlation",
            "next_absolute_correlation",
        }
        missing = sorted(required - set(row))
        if missing:
            raise ValueError(f"{best_path}: missing columns: {', '.join(missing)}")
        margin = float(row["absolute_correlation"]) - float(
            row["next_absolute_correlation"]
        )
        output.append(
            {
                "data_set": data_set,
                "dimension": dimension,
                "n_components": str(component_rows),
                "smith09_map": row["smith09_map"],
                "network": row["network"],
                "analysis_priority": row["analysis_priority"],
                "best_component": row["best_component"],
                "correlation": row["correlation"],
                "absolute_correlation": row["absolute_correlation"],
                "sign": row["sign"],
                "next_component": row["next_component"],
                "next_correlation": row["next_correlation"],
                "next_absolute_correlation": row["next_absolute_correlation"],
                "absolute_correlation_margin": f"{margin:.8g}",
            }
        )
    return output


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fsl-dir",
        type=Path,
        default=repo_root / "derivatives" / "fsl",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Defaults to derivatives/fsl/diagnostics/smith09_ica_comparison.tsv",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    fsl_dir = args.fsl_dir.expanduser().resolve()
    output = (
        args.output.expanduser().resolve()
        if args.output
        else fsl_dir / "diagnostics" / "smith09_ica_comparison.tsv"
    )
    try:
        rows = []
        for analysis in ANALYSES:
            rows.extend(read_analysis(fsl_dir, *analysis))
    except (OSError, ValueError) as error:
        raise SystemExit(f"ERROR: {error}") from error

    fieldnames = list(rows[0])
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=fieldnames,
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    print(f"Analyses: {len(ANALYSES)}")
    print(f"Network matches: {len(rows)}")
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
