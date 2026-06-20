#!/usr/bin/env python3
"""Summarize task-rest MRIQC IQMs and flag runs that need review."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunIQM:
    participant: str
    session: str
    task: str
    acquisition: str
    run: str
    echo: str
    tsnr: float
    fd_mean: float
    source: str


def percentile(values: list[float], quantile: float) -> float:
    """Return a linearly interpolated percentile, matching common data tools."""
    if not values:
        raise ValueError("Cannot calculate a percentile from an empty list")
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + fraction * (ordered[upper] - ordered[lower])


def tukey_bounds(values: list[float]) -> tuple[float, float, float, float, float]:
    q1 = percentile(values, 0.25)
    q3 = percentile(values, 0.75)
    iqr = q3 - q1
    return q1, q3, iqr, q1 - 1.5 * iqr, q3 + 1.5 * iqr


def entities_from_name(path: Path) -> dict[str, str]:
    entities: dict[str, str] = {}
    name = path.name.removesuffix("_bold.json")
    for part in name.split("_"):
        if "-" in part:
            key, value = part.split("-", 1)
            entities[key] = value
    return entities


def required_number(data: dict[str, object], key: str, path: Path) -> float:
    value = data.get(key)
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise ValueError(f"{path}: missing or invalid {key}") from error
    if not math.isfinite(number):
        raise ValueError(f"{path}: {key} is not finite")
    return number


def read_iqms(mriqc_dir: Path, task: str) -> list[RunIQM]:
    paths = sorted(mriqc_dir.glob(f"sub-*/**/*_task-{task}_*_bold.json"))
    if not paths:
        raise ValueError(f"No task-{task} BOLD IQM files found in: {mriqc_dir}")

    runs = []
    for path in paths:
        entities = entities_from_name(path)
        if "sub" not in entities:
            raise ValueError(f"Cannot determine participant from: {path}")
        with path.open() as stream:
            data = json.load(stream)
        runs.append(
            RunIQM(
                participant=f"sub-{entities['sub']}",
                session=entities.get("ses", ""),
                task=entities.get("task", task),
                acquisition=entities.get("acq", ""),
                run=entities.get("run", ""),
                echo=entities.get("echo", ""),
                tsnr=required_number(data, "tsnr", path),
                fd_mean=required_number(data, "fd_mean", path),
                source=str(path.resolve()),
            )
        )
    return runs


def fmt(value: float) -> str:
    return f"{value:.6g}"


def write_run_report(
    path: Path,
    runs: list[RunIQM],
    tsnr_lower: float,
    fd_upper: float,
    fd_threshold: float,
) -> list[dict[str, str]]:
    rows = []
    for run in runs:
        low_tsnr = run.tsnr < tsnr_lower
        high_fd = run.fd_mean > fd_upper
        fd_threshold_flag = run.fd_mean > fd_threshold
        review = low_tsnr or high_fd or fd_threshold_flag
        row = {
            **{key: str(value) for key, value in asdict(run).items()},
            "tsnr": fmt(run.tsnr),
            "fd_mean": fmt(run.fd_mean),
            "low_tsnr": str(low_tsnr).lower(),
            "high_fd_mean": str(high_fd).lower(),
            f"fd_mean_gt_{fd_threshold:g}": str(fd_threshold_flag).lower(),
            "review": str(review).lower(),
        }
        rows.append(row)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    return rows


def write_bounds(
    path: Path,
    tsnr: tuple[float, float, float, float, float],
    fd_mean: tuple[float, float, float, float, float],
    fd_threshold: float,
) -> None:
    rows = [
        {
            "metric": "tsnr",
            "q1": fmt(tsnr[0]),
            "q3": fmt(tsnr[1]),
            "iqr": fmt(tsnr[2]),
            "review_rule": f"value < {fmt(tsnr[3])}",
        },
        {
            "metric": "fd_mean",
            "q1": fmt(fd_mean[0]),
            "q3": fmt(fd_mean[1]),
            "iqr": fmt(fd_mean[2]),
            "review_rule": f"value > {fmt(fd_mean[4])} or value > {fd_threshold:g}",
        },
    ]
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def write_subject_summary(
    path: Path, runs: list[RunIQM], rows: list[dict[str, str]]
) -> None:
    run_rows = {row["source"]: row for row in rows}
    grouped: dict[str, list[RunIQM]] = defaultdict(list)
    for run in runs:
        grouped[run.participant].append(run)

    output = []
    threshold_column = next(key for key in rows[0] if key.startswith("fd_mean_gt_"))
    for participant, participant_runs in sorted(grouped.items()):
        flags = [run_rows[run.source] for run in participant_runs]
        output.append(
            {
                "participant": participant,
                "n_runs": str(len(participant_runs)),
                "mean_tsnr": fmt(
                    sum(run.tsnr for run in participant_runs) / len(participant_runs)
                ),
                "mean_fd_mean": fmt(
                    sum(run.fd_mean for run in participant_runs) / len(participant_runs)
                ),
                "n_low_tsnr": str(sum(row["low_tsnr"] == "true" for row in flags)),
                "n_high_fd_mean": str(
                    sum(row["high_fd_mean"] == "true" for row in flags)
                ),
                f"n_{threshold_column}": str(
                    sum(row[threshold_column] == "true" for row in flags)
                ),
                "n_review": str(sum(row["review"] == "true" for row in flags)),
            }
        )

    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(output[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(output)


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    derivatives = Path(os.environ.get("DERIVATIVES_ROOT", repo_root / "derivatives"))
    parser = argparse.ArgumentParser(
        description="Flag low-tSNR and high-motion task-rest MRIQC runs."
    )
    parser.add_argument(
        "--mriqcDir",
        "--mriqc-dir",
        dest="mriqc_dir",
        type=Path,
        default=Path(os.environ.get("MRIQC_OUTPUT_DIR", derivatives / "mriqc")),
    )
    parser.add_argument(
        "--outDir",
        "--output-dir",
        dest="output_dir",
        type=Path,
        default=derivatives / "qc",
    )
    parser.add_argument("--task", default=os.environ.get("TASK_ID", "rest"))
    parser.add_argument(
        "--fd-threshold",
        type=float,
        default=0.5,
        help="Also flag runs above this mean-FD threshold (default: 0.5 mm).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    mriqc_dir = args.mriqc_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    if not mriqc_dir.is_dir():
        raise SystemExit(f"MRIQC directory not found: {mriqc_dir}")
    if args.fd_threshold <= 0:
        raise SystemExit("--fd-threshold must be greater than zero")

    try:
        runs = read_iqms(mriqc_dir, args.task)
        tsnr = tukey_bounds([run.tsnr for run in runs])
        fd_mean = tukey_bounds([run.fd_mean for run in runs])
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"ERROR: {error}") from error

    output_dir.mkdir(parents=True, exist_ok=True)
    run_report = output_dir / f"task-{args.task}_mriqc_outliers.tsv"
    bounds_report = output_dir / f"task-{args.task}_mriqc_bounds.tsv"
    subject_report = output_dir / f"task-{args.task}_mriqc_subject_summary.tsv"
    rows = write_run_report(run_report, runs, tsnr[3], fd_mean[4], args.fd_threshold)
    write_bounds(bounds_report, tsnr, fd_mean, args.fd_threshold)
    write_subject_summary(subject_report, runs, rows)

    review_count = sum(row["review"] == "true" for row in rows)
    print(f"Runs reviewed: {len(runs)}")
    print(f"Runs flagged: {review_count}")
    print(f"Low-tSNR fence: {fmt(tsnr[3])}")
    print(f"High-FD fence: {fmt(fd_mean[4])}; absolute threshold: {args.fd_threshold:g}")
    print(f"Wrote {run_report}")
    print(f"Wrote {bounds_report}")
    print(f"Wrote {subject_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
