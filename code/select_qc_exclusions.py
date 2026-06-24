#!/usr/bin/env python3
"""Apply Tukey boxplots to mean QC magnitude across three orthogonal contrasts."""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path


CONDITIONS = ("sham", "rtpj", "vlpfc", "both")
METRICS = ("tsnr", "fd_mean")
CONTRASTS = (
    (
        "active_mean_minus_sham",
        {"sham": -1.0, "rtpj": 1 / 3, "vlpfc": 1 / 3, "both": 1 / 3},
    ),
    (
        "both_minus_mean_rtpj_vlpfc",
        {"rtpj": -0.5, "vlpfc": -0.5, "both": 1.0},
    ),
    ("rtpj_minus_vlpfc", {"rtpj": 1.0, "vlpfc": -1.0}),
)


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (position - lower) * (ordered[upper] - ordered[lower])


def tukey_upper_fence(values: list[float]) -> tuple[float, float, float, float]:
    q1 = percentile(values, 0.25)
    q3 = percentile(values, 0.75)
    iqr = q3 - q1
    return q1, q3, iqr, q3 + 1.5 * iqr


def read_complete_profiles(path: Path) -> dict[str, dict[str, dict[str, str]]]:
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        required = {"participant", "condition", *METRICS}
        missing = required.difference(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path} is missing columns: {sorted(missing)}")
        rows = list(reader)

    profiles: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in rows:
        participant = row["participant"]
        condition = row["condition"].lower()
        if condition not in CONDITIONS:
            continue
        if condition in profiles[participant]:
            raise ValueError(f"Duplicate {participant} {condition} row")
        profiles[participant][condition] = row

    complete = {
        participant: profile
        for participant, profile in profiles.items()
        if set(profile) == set(CONDITIONS)
    }
    if not complete:
        raise ValueError("No participant had all four task-rest conditions")
    return dict(sorted(complete.items()))


def signed_contrast(
    profile: dict[str, dict[str, str]], metric: str, weights: dict[str, float]
) -> float:
    return sum(
        float(profile[condition][metric]) * weight
        for condition, weight in weights.items()
    )


def select_participants(
    profiles: dict[str, dict[str, dict[str, str]]], required_metric_flags: int
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    contrasts: dict[str, dict[str, dict[str, float]]] = defaultdict(dict)
    scores: dict[str, dict[str, float]] = defaultdict(dict)
    for participant, profile in profiles.items():
        for metric in METRICS:
            metric_contrasts = {
                label: signed_contrast(profile, metric, weights)
                for label, weights in CONTRASTS
            }
            contrasts[participant][metric] = metric_contrasts
            scores[participant][metric] = sum(
                abs(value) for value in metric_contrasts.values()
            ) / len(CONTRASTS)

    bounds: dict[str, tuple[float, float, float, float]] = {}
    bound_rows: list[dict[str, str]] = []
    for metric in METRICS:
        values = [scores[participant][metric] for participant in scores]
        metric_bounds = tukey_upper_fence(values)
        bounds[metric] = metric_bounds
        bound_rows.append(
            {
                "metric": metric,
                "n_participants": str(len(values)),
                "aggregate": (
                    "mean absolute magnitude across three orthogonal contrasts"
                ),
                "q1": f"{metric_bounds[0]:.8g}",
                "q3": f"{metric_bounds[1]:.8g}",
                "iqr": f"{metric_bounds[2]:.8g}",
                "upper_fence": f"{metric_bounds[3]:.8g}",
                "outlier_rule": "mean absolute contrast > Q3 + 1.5*IQR",
            }
        )

    output: list[dict[str, str]] = []
    for participant in scores:
        flags = {
            metric: scores[participant][metric] > bounds[metric][3]
            for metric in METRICS
        }
        flag_count = sum(flags.values())
        row = {"participant": participant, "n_contrasts": str(len(CONTRASTS))}
        for metric in METRICS:
            for label, _ in CONTRASTS:
                row[f"{label}_delta_{metric}"] = f"{contrasts[participant][metric][label]:.8g}"
            row[f"mean_abs_delta_{metric}"] = f"{scores[participant][metric]:.8g}"
            row[f"{metric}_outlier"] = str(flags[metric]).lower()
        row["n_metric_outliers"] = str(flag_count)
        row["decision"] = "exclude" if flag_count >= required_metric_flags else "include"
        output.append(row)
    return output, bound_rows


def write_tsv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def write_exclusion_list(
    path: Path, rows: list[dict[str, str]], required_metric_flags: int
) -> None:
    excluded = [row["participant"] for row in rows if row["decision"] == "exclude"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Task-rest differential-QC exclusions.\n"
        "# Average the absolute magnitude of three orthogonal condition contrasts\n"
        "# separately for tSNR and mean FD, then apply the Tukey upper fence.\n"
        f"# Exclude when both ({required_metric_flags}) metric summaries are outliers.\n"
        f"# Excluded participants: {len(excluded)}.\n"
        + "".join(f"{participant}\n" for participant in excluded)
    )


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    qc_dir = repo_root / "derivatives" / "qc"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mriqc-runs",
        type=Path,
        default=qc_dir / "task-rest_mriqc_outliers.tsv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=qc_dir / "task-rest_qc_exclusions.tsv",
    )
    parser.add_argument(
        "--bounds-output",
        type=Path,
        default=qc_dir / "task-rest_qc_contrast_average_bounds.tsv",
    )
    parser.add_argument(
        "--exclude-list",
        type=Path,
        default=repo_root / "code" / "exclude_qc_outliers.txt",
    )
    parser.add_argument("--required-metric-flags", type=int, default=len(METRICS))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 1 <= args.required_metric_flags <= len(METRICS):
        raise ValueError(f"--required-metric-flags must be between 1 and {len(METRICS)}")
    profiles = read_complete_profiles(args.mriqc_runs.resolve())
    decisions, bounds = select_participants(profiles, args.required_metric_flags)
    write_tsv(args.output.resolve(), decisions)
    write_tsv(args.bounds_output.resolve(), bounds)
    write_exclusion_list(
        args.exclude_list.resolve(), decisions, args.required_metric_flags
    )
    excluded = [
        row["participant"] for row in decisions if row["decision"] == "exclude"
    ]
    print(f"Participants evaluated: {len(decisions)}")
    print(f"Participants excluded: {len(excluded)}")
    print(f"Excluded: {','.join(excluded) if excluded else 'none'}")
    print(f"Wrote {args.output.resolve()}")
    print(f"Wrote {args.bounds_output.resolve()}")
    print(f"Wrote {args.exclude_list.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
