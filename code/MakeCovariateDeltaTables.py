#!/usr/bin/env python3
"""Write compact subject-level covariate delta tables for planned contrasts."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path


CONTRAST_SPECS: dict[str, dict[str, str | float]] = {
    "both-minus-sham": {
        "source": "both-minus-sham",
        "sign": 1.0,
        "label": "BOTH > SHAM",
        "weights": "both=1, sham=-1",
    },
    "both-minus-rtpj": {
        "source": "both-minus-rtpj",
        "sign": 1.0,
        "label": "BOTH > RTPJ",
        "weights": "both=1, rtpj=-1",
    },
    "both-minus-vlpfc": {
        "source": "both-minus-vlpfc",
        "sign": 1.0,
        "label": "BOTH > VLPFC",
        "weights": "both=1, vlpfc=-1",
    },
    "both-minus-mean-rtpj-vlpfc": {
        "source": "both-minus-mean-rtpj-vlpfc",
        "sign": 1.0,
        "label": "BOTH > mean(RTPJ, VLPFC)",
        "weights": "both=1, rtpj=-0.5, vlpfc=-0.5",
    },
    "vlpfc-minus-rtpj": {
        "source": "rtpj-minus-vlpfc",
        "sign": -1.0,
        "label": "VLPFC > RTPJ",
        "weights": "vlpfc=1, rtpj=-1",
    },
    "vlpfc-minus-sham": {
        "source": "vlpfc-minus-sham",
        "sign": 1.0,
        "label": "VLPFC > SHAM",
        "weights": "vlpfc=1, sham=-1",
    },
    "rtpj-minus-sham": {
        "source": "rtpj-minus-sham",
        "sign": 1.0,
        "label": "RTPJ > SHAM",
        "weights": "rtpj=1, sham=-1",
    },
}

CONTRAST_SETS = {
    "core": (
        "both-minus-sham",
        "both-minus-mean-rtpj-vlpfc",
        "vlpfc-minus-rtpj",
        "vlpfc-minus-sham",
        "rtpj-minus-sham",
    ),
    "primary": (
        "both-minus-sham",
        "both-minus-rtpj",
        "both-minus-vlpfc",
        "both-minus-mean-rtpj-vlpfc",
        "vlpfc-minus-rtpj",
        "vlpfc-minus-sham",
        "rtpj-minus-sham",
    ),
}

FIELDS = (
    "participant",
    "contrast",
    "contrast_label",
    "weights",
    "complete_conditions",
    "missing_conditions",
    "complete_delta_covariates",
    "missing_delta_covariates",
    "delta_blink",
    "delta_pupil",
    "delta_fdmean",
)


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, str]], fieldnames: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=fieldnames, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def is_complete_delta_row(row: dict[str, str]) -> bool:
    return row["complete_delta_covariates"].lower() == "true"


def parse_contrast_list(value: str) -> list[str]:
    lowered = value.strip().lower()
    if lowered in CONTRAST_SETS:
        return list(CONTRAST_SETS[lowered])

    contrasts: list[str] = []
    for item in value.split(","):
        contrast = item.strip()
        if not contrast:
            continue
        if contrast not in CONTRAST_SPECS:
            known = ", ".join(sorted(CONTRAST_SPECS))
            raise ValueError(f"Unknown contrast '{contrast}'. Known contrasts: {known}")
        if contrast in contrasts:
            raise ValueError(f"Duplicate contrast: {contrast}")
        contrasts.append(contrast)
    if not contrasts:
        raise ValueError("At least one contrast is required")
    return contrasts


def fmt_flipped(value: str, sign: float) -> str:
    if value.strip().lower() in {"", "n/a", "nan", "none"}:
        return "n/a"
    return f"{float(value) * sign:.10g}"


def index_covariates(rows: list[dict[str, str]]) -> dict[tuple[str, str], dict[str, str]]:
    required = {
        "participant",
        "contrast",
        "complete",
        "missing_conditions",
        "delta_fd_mean",
        "delta_mean_pupil_area",
        "delta_blink_rate_per_min",
    }
    if not rows:
        raise ValueError("Input covariate table has no rows")
    missing = required.difference(rows[0])
    if missing:
        raise ValueError(f"Input covariate table is missing columns: {sorted(missing)}")

    indexed: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        key = (row["participant"], row["contrast"])
        if key in indexed:
            raise ValueError(f"Duplicate covariate row for {key[0]} {key[1]}")
        indexed[key] = row
    return indexed


def build_delta_rows(
    covariate_rows: list[dict[str, str]], contrasts: list[str]
) -> list[dict[str, str]]:
    indexed = index_covariates(covariate_rows)
    participants = sorted({participant for participant, _contrast in indexed})
    output: list[dict[str, str]] = []

    for contrast in contrasts:
        spec = CONTRAST_SPECS[contrast]
        source = str(spec["source"])
        sign = float(spec["sign"])
        for participant in participants:
            source_row = indexed.get((participant, source))
            if source_row is None:
                row = {
                    "participant": participant,
                    "contrast": contrast,
                    "contrast_label": str(spec["label"]),
                    "weights": str(spec["weights"]),
                    "complete_conditions": "false",
                    "missing_conditions": source,
                    "complete_delta_covariates": "false",
                    "missing_delta_covariates": "blink,pupil,fdmean",
                    "delta_blink": "n/a",
                    "delta_pupil": "n/a",
                    "delta_fdmean": "n/a",
                }
            else:
                delta_values = {
                    "blink": fmt_flipped(source_row["delta_blink_rate_per_min"], sign),
                    "pupil": fmt_flipped(source_row["delta_mean_pupil_area"], sign),
                    "fdmean": fmt_flipped(source_row["delta_fd_mean"], sign),
                }
                missing_delta_metrics = [
                    metric for metric, value in delta_values.items() if value == "n/a"
                ]
                row = {
                    "participant": participant,
                    "contrast": contrast,
                    "contrast_label": str(spec["label"]),
                    "weights": str(spec["weights"]),
                    "complete_conditions": source_row["complete"],
                    "missing_conditions": source_row["missing_conditions"],
                    "complete_delta_covariates": str(
                        source_row["complete"].lower() == "true"
                        and not missing_delta_metrics
                    ).lower(),
                    "missing_delta_covariates": ",".join(missing_delta_metrics),
                    "delta_blink": delta_values["blink"],
                    "delta_pupil": delta_values["pupil"],
                    "delta_fdmean": delta_values["fdmean"],
                }
            output.append(row)
    return output


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    qc_dir = repo_root / "derivatives" / "qc"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=qc_dir / "task-rest_group_covariates.tsv",
        help="Contrast-level covariates from MakeGroupCovariates.py.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=qc_dir / "covariate_delta_tables",
        help="Directory for compact combined and per-contrast TSV files.",
    )
    parser.add_argument(
        "--contrasts",
        default="primary",
        help="Contrast set ('primary' or 'core') or comma-separated contrast names.",
    )
    parser.add_argument(
        "--include-incomplete",
        action="store_true",
        help="Keep rows with missing pupil/blink/FD deltas in the main tables.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    contrasts = parse_contrast_list(args.contrasts)
    all_rows = build_delta_rows(read_tsv(args.input.resolve()), contrasts)
    missing_rows = [row for row in all_rows if not is_complete_delta_row(row)]
    rows = all_rows if args.include_incomplete else [row for row in all_rows if is_complete_delta_row(row)]

    output_dir = args.output_dir.resolve()
    combined = output_dir / "task-rest_covariate_deltas.tsv"
    missingness = output_dir / "task-rest_covariate_delta_missingness.tsv"
    write_tsv(combined, rows, FIELDS)
    write_tsv(missingness, missing_rows, FIELDS)

    for contrast in contrasts:
        contrast_rows = [row for row in rows if row["contrast"] == contrast]
        contrast_path = output_dir / f"task-rest_contrast-{contrast}_covariate-deltas.tsv"
        write_tsv(contrast_path, contrast_rows, FIELDS)

    print(f"Contrasts summarized: {len(contrasts)}")
    print(f"Rows written: {len(rows)}")
    print(f"Incomplete rows written to missingness audit: {len(missing_rows)}")
    print(f"Wrote {combined}")
    print(f"Wrote {missingness}")
    print(f"Wrote per-contrast tables under {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
