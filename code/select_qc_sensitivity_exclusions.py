#!/usr/bin/env python3
"""Select differential-motion exclusions for the task-rest sensitivity analysis."""

from __future__ import annotations

import argparse
import csv
import math
from collections import defaultdict
from pathlib import Path


CONTRASTS = (
    "both_minus_sham",
    "both_minus_rtpj",
    "both_minus_vlpfc",
    "rtpj_minus_vlpfc",
    "rtpj_minus_sham",
    "vlpfc_minus_sham",
    "both_minus_mean_rtpj_vlpfc",
)
METRICS = ("delta_tsnr", "delta_fd_mean", "delta_fd_perc")


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (position - lower) * (ordered[upper] - ordered[lower])


def absolute_tukey_bounds(values: list[float]) -> tuple[float, float, float, float]:
    absolute = [abs(value) for value in values]
    q1 = percentile(absolute, 0.25)
    q3 = percentile(absolute, 0.75)
    iqr = q3 - q1
    return q1, q3, iqr, q3 + 1.5 * iqr


def read_complete_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        required = {"participant", "contrast", "complete", *METRICS}
        missing = required.difference(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path} is missing columns: {sorted(missing)}")
        rows = [row for row in reader if row["complete"].lower() == "true"]
    if not rows:
        raise ValueError(f"No complete condition contrasts found in: {path}")
    return rows


def select_participants(
    rows: list[dict[str, str]], minimum_motion_coflags: int
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    contrast_sets: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        contrast_sets[row["participant"]].add(row["contrast"])
    eligible = {
        participant
        for participant, contrasts in contrast_sets.items()
        if set(CONTRASTS) <= contrasts
    }
    rows = [row for row in rows if row["participant"] in eligible]
    if not rows:
        raise ValueError("No participant had all seven complete condition contrasts")

    bounds: dict[tuple[str, str], tuple[float, float, float, float]] = {}
    bound_rows: list[dict[str, str]] = []
    for contrast in CONTRASTS:
        contrast_rows = [row for row in rows if row["contrast"] == contrast]
        if not contrast_rows:
            raise ValueError(f"No complete rows found for contrast: {contrast}")
        for metric in METRICS:
            values = [float(row[metric]) for row in contrast_rows]
            metric_bounds = absolute_tukey_bounds(values)
            bounds[(contrast, metric)] = metric_bounds
            bound_rows.append(
                {
                    "contrast": contrast,
                    "metric": metric,
                    "n_complete": str(len(values)),
                    "absolute_q1": f"{metric_bounds[0]:.8g}",
                    "absolute_q3": f"{metric_bounds[1]:.8g}",
                    "absolute_iqr": f"{metric_bounds[2]:.8g}",
                    "absolute_upper_fence": f"{metric_bounds[3]:.8g}",
                    "review_rule": "absolute condition difference above upper fence",
                }
            )

    by_participant: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in rows:
        participant = row["participant"]
        contrast = row["contrast"]
        if contrast in by_participant[participant]:
            raise ValueError(f"Duplicate {participant} {contrast} row")
        by_participant[participant][contrast] = row

    output: list[dict[str, str]] = []
    for participant, participant_rows in sorted(by_participant.items()):
        missing = set(CONTRASTS).difference(participant_rows)
        if missing:
            continue
        flags = {metric: [] for metric in METRICS}
        motion_coflags = []
        for contrast in CONTRASTS:
            row = participant_rows[contrast]
            for metric in METRICS:
                if abs(float(row[metric])) > bounds[(contrast, metric)][3]:
                    flags[metric].append(contrast)
            if (
                contrast in flags["delta_fd_mean"]
                and contrast in flags["delta_fd_perc"]
            ):
                motion_coflags.append(contrast)

        exclude = len(motion_coflags) >= minimum_motion_coflags
        output.append(
            {
                "participant": participant,
                "n_complete_contrasts": str(len(CONTRASTS)),
                "absolute_tsnr_outlier_count": str(len(flags["delta_tsnr"])),
                "absolute_fd_mean_outlier_count": str(len(flags["delta_fd_mean"])),
                "absolute_fd_perc_outlier_count": str(len(flags["delta_fd_perc"])),
                "paired_motion_outlier_count": str(len(motion_coflags)),
                "paired_motion_outlier_contrasts": ",".join(motion_coflags),
                "decision": "exclude_sensitivity" if exclude else "include_sensitivity",
            }
        )
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
    path: Path, rows: list[dict[str, str]], minimum_motion_coflags: int
) -> None:
    excluded = [row["participant"] for row in rows if row["decision"] == "exclude_sensitivity"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Differential-motion QC sensitivity exclusions.\n"
        "# For each of seven planned condition contrasts, apply a Tukey 1.5-IQR\n"
        "# upper fence to absolute mean-FD and absolute FD>0.20-mm percentage\n"
        f"# differences. Exclude after paired flags on at least {minimum_motion_coflags} contrasts.\n"
        + "".join(f"{participant}\n" for participant in excluded)
    )


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    qc_dir = repo_root / "derivatives" / "qc"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--condition-contrasts",
        type=Path,
        default=qc_dir / "task-rest_mriqc_condition_contrasts.tsv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=qc_dir / "task-rest_qc_sensitivity_exclusions.tsv",
    )
    parser.add_argument(
        "--bounds-output",
        type=Path,
        default=qc_dir / "task-rest_qc_sensitivity_abs_bounds.tsv",
    )
    parser.add_argument(
        "--exclude-list",
        type=Path,
        default=repo_root / "code" / "exclude_qc_outliers.txt",
    )
    parser.add_argument("--minimum-motion-coflags", type=int, default=2)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.minimum_motion_coflags < 1:
        raise ValueError("--minimum-motion-coflags must be positive")
    rows = read_complete_rows(args.condition_contrasts.resolve())
    decisions, bounds = select_participants(rows, args.minimum_motion_coflags)
    write_tsv(args.output.resolve(), decisions)
    write_tsv(args.bounds_output.resolve(), bounds)
    write_exclusion_list(
        args.exclude_list.resolve(), decisions, args.minimum_motion_coflags
    )
    excluded = [row["participant"] for row in decisions if row["decision"].startswith("exclude")]
    print(f"Participants evaluated: {len(decisions)}")
    print(f"Participants excluded from sensitivity: {len(excluded)}")
    print(f"Excluded: {','.join(excluded) if excluded else 'none'}")
    print(f"Wrote {args.output.resolve()}")
    print(f"Wrote {args.bounds_output.resolve()}")
    print(f"Wrote {args.exclude_list.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
