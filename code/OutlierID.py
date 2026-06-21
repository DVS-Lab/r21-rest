#!/usr/bin/env python3
"""Summarize task-rest MRIQC IQMs and flag subjects and runs for review."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path


CONDITIONS = {"sham", "rtpj", "vlpfc", "both"}
CONTRASTS = (
    ("both_minus_sham", {"both": 1.0}, {"sham": 1.0}),
    ("both_minus_rtpj", {"both": 1.0}, {"rtpj": 1.0}),
    ("both_minus_vlpfc", {"both": 1.0}, {"vlpfc": 1.0}),
    ("rtpj_minus_vlpfc", {"rtpj": 1.0}, {"vlpfc": 1.0}),
    ("rtpj_minus_sham", {"rtpj": 1.0}, {"sham": 1.0}),
    ("vlpfc_minus_sham", {"vlpfc": 1.0}, {"sham": 1.0}),
    (
        "both_minus_mean_rtpj_vlpfc",
        {"both": 1.0},
        {"rtpj": 0.5, "vlpfc": 0.5},
    ),
)
CONTRAST_METRICS = ("tsnr", "fd_mean", "fd_perc")


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
    fd_num: int
    fd_perc: float
    source: str
    condition: str = ""


@dataclass(frozen=True)
class SubjectIQM:
    participant: str
    n_runs: int
    mean_tsnr: float
    min_tsnr: float
    mean_fd_mean: float
    max_fd_mean: float
    total_fd_num: int
    mean_fd_perc: float
    max_fd_perc: float


@dataclass(frozen=True)
class ContrastIQM:
    participant: str
    contrast: str
    condition_a: str
    condition_b: str
    complete: bool
    a_tsnr: float | None
    b_tsnr: float | None
    delta_tsnr: float | None
    a_fd_mean: float | None
    b_fd_mean: float | None
    delta_fd_mean: float | None
    a_fd_perc: float | None
    b_fd_perc: float | None
    delta_fd_perc: float | None


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


def find_events(iqm_path: Path, bids_dir: Path) -> Path:
    entities = entities_from_name(iqm_path)
    participant = f"sub-{entities['sub']}"
    events_name = iqm_path.name.removesuffix("_bold.json") + "_events.tsv"
    matches = sorted((bids_dir / participant).rglob(events_name))
    if len(matches) != 1:
        raise ValueError(
            f"Expected one events file for {iqm_path.name}; found {len(matches)}"
        )
    return matches[0]


def condition_from_events(path: Path) -> str:
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames is None or "trial_type" not in reader.fieldnames:
            raise ValueError(f"{path}: missing trial_type column")
        conditions = {
            (row.get("trial_type") or "").strip().lower()
            for row in reader
            if (row.get("trial_type") or "").strip()
        }
    if not conditions:
        return ""
    if len(conditions) != 1:
        raise ValueError(
            f"{path}: expected one trial_type; found {', '.join(sorted(conditions))}"
        )
    condition = conditions.pop()
    if condition not in CONDITIONS:
        raise ValueError(
            f"{path}: unknown trial_type {condition}; expected "
            + ", ".join(sorted(CONDITIONS))
        )
    return condition


def read_iqms(
    mriqc_dir: Path,
    task: str,
    bids_dir: Path | None = None,
) -> list[RunIQM]:
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
                fd_num=int(required_number(data, "fd_num", path)),
                fd_perc=required_number(data, "fd_perc", path),
                source=str(path.resolve()),
                condition=(
                    condition_from_events(find_events(path, bids_dir))
                    if bids_dir is not None
                    else ""
                ),
            )
        )
    return runs


def fmt(value: float) -> str:
    return f"{value:.6g}"


def fmt_optional(value: float | None) -> str:
    return "n/a" if value is None else fmt(value)


def write_run_report(
    path: Path,
    runs: list[RunIQM],
    tsnr_lower: float,
    fd_upper: float,
    fd_threshold: float,
    tsnr_threshold: float,
) -> list[dict[str, str]]:
    rows = []
    for run in runs:
        low_tsnr = run.tsnr < tsnr_lower
        tsnr_threshold_flag = run.tsnr < tsnr_threshold
        high_fd = run.fd_mean > fd_upper
        fd_threshold_flag = run.fd_mean > fd_threshold
        high_fd_perc = run.fd_perc > 50
        review = (
            low_tsnr
            or tsnr_threshold_flag
            or high_fd
            or fd_threshold_flag
            or high_fd_perc
        )
        row = {
            **{key: str(value) for key, value in asdict(run).items()},
            "tsnr": fmt(run.tsnr),
            "fd_mean": fmt(run.fd_mean),
            "fd_perc": fmt(run.fd_perc),
            "low_tsnr": str(low_tsnr).lower(),
            "tsnr_lt_threshold": str(tsnr_threshold_flag).lower(),
            "high_fd_mean": str(high_fd).lower(),
            f"fd_mean_gt_{fd_threshold:g}": str(fd_threshold_flag).lower(),
            "fd_perc_gt_50": str(high_fd_perc).lower(),
            "review": str(review).lower(),
        }
        rows.append(row)

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
    return rows


def write_bounds(
    path: Path,
    bounds: list[tuple[str, tuple[float, float, float, float, float], str]],
) -> None:
    rows = []
    for metric, values, review_rule in bounds:
        rows.append(
            {
                "metric": metric,
                "q1": fmt(values[0]),
                "q3": fmt(values[1]),
                "iqr": fmt(values[2]),
                "lower_fence": fmt(values[3]),
                "upper_fence": fmt(values[4]),
                "review_rule": review_rule,
            }
        )
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def summarize_subjects(runs: list[RunIQM]) -> list[SubjectIQM]:
    grouped: dict[str, list[RunIQM]] = defaultdict(list)
    for run in runs:
        grouped[run.participant].append(run)

    subjects = []
    for participant, participant_runs in sorted(grouped.items()):
        n_runs = len(participant_runs)
        subjects.append(
            SubjectIQM(
                participant=participant,
                n_runs=n_runs,
                mean_tsnr=sum(run.tsnr for run in participant_runs) / n_runs,
                min_tsnr=min(run.tsnr for run in participant_runs),
                mean_fd_mean=sum(run.fd_mean for run in participant_runs) / n_runs,
                max_fd_mean=max(run.fd_mean for run in participant_runs),
                total_fd_num=sum(run.fd_num for run in participant_runs),
                mean_fd_perc=sum(run.fd_perc for run in participant_runs) / n_runs,
                max_fd_perc=max(run.fd_perc for run in participant_runs),
            )
        )
    return subjects


def weighted_metric(
    condition_runs: dict[str, RunIQM], weights: dict[str, float], metric: str
) -> float:
    return sum(
        weight * float(getattr(condition_runs[condition], metric))
        for condition, weight in weights.items()
    )


def condition_label(weights: dict[str, float]) -> str:
    if len(weights) == 1:
        return next(iter(weights))
    return "mean_" + "_".join(weights)


def calculate_condition_contrasts(runs: list[RunIQM]) -> list[ContrastIQM]:
    grouped: dict[str, list[RunIQM]] = defaultdict(list)
    for run in runs:
        grouped[run.participant].append(run)

    contrasts = []
    for participant, participant_runs in sorted(grouped.items()):
        condition_runs: dict[str, RunIQM] = {}
        for run in participant_runs:
            if not run.condition:
                continue
            if run.condition in condition_runs:
                raise ValueError(
                    f"{participant}: more than one run labeled {run.condition}"
                )
            condition_runs[run.condition] = run

        for contrast, a_weights, b_weights in CONTRASTS:
            required = set(a_weights) | set(b_weights)
            complete = required <= set(condition_runs)
            values: dict[str, float | None] = {}
            for metric in CONTRAST_METRICS:
                if complete:
                    a_value = weighted_metric(condition_runs, a_weights, metric)
                    b_value = weighted_metric(condition_runs, b_weights, metric)
                    values[f"a_{metric}"] = a_value
                    values[f"b_{metric}"] = b_value
                    values[f"delta_{metric}"] = a_value - b_value
                else:
                    values[f"a_{metric}"] = None
                    values[f"b_{metric}"] = None
                    values[f"delta_{metric}"] = None
            contrasts.append(
                ContrastIQM(
                    participant=participant,
                    contrast=contrast,
                    condition_a=condition_label(a_weights),
                    condition_b=condition_label(b_weights),
                    complete=complete,
                    **values,
                )
            )
    return contrasts


def condition_contrast_bounds(
    contrasts: list[ContrastIQM],
) -> dict[tuple[str, str], tuple[float, float, float, float, float]]:
    bounds = {}
    for contrast, _, _ in CONTRASTS:
        for metric in CONTRAST_METRICS:
            values = [
                float(getattr(row, f"delta_{metric}"))
                for row in contrasts
                if row.contrast == contrast
                and getattr(row, f"delta_{metric}") is not None
            ]
            if values:
                bounds[(contrast, metric)] = tukey_bounds(values)
    return bounds


def write_condition_contrast_report(
    path: Path,
    contrasts: list[ContrastIQM],
    bounds: dict[tuple[str, str], tuple[float, float, float, float, float]],
) -> list[dict[str, str]]:
    output = []
    for contrast in contrasts:
        flags = {}
        for metric in CONTRAST_METRICS:
            delta = getattr(contrast, f"delta_{metric}")
            metric_bounds = bounds.get((contrast.contrast, metric))
            flags[metric] = bool(
                delta is not None
                and metric_bounds is not None
                and (delta < metric_bounds[3] or delta > metric_bounds[4])
            )
        n_outliers = sum(flags.values())
        output.append(
            {
                "participant": contrast.participant,
                "contrast": contrast.contrast,
                "condition_a": contrast.condition_a,
                "condition_b": contrast.condition_b,
                "complete": str(contrast.complete).lower(),
                "a_tsnr": fmt_optional(contrast.a_tsnr),
                "b_tsnr": fmt_optional(contrast.b_tsnr),
                "delta_tsnr": fmt_optional(contrast.delta_tsnr),
                "a_fd_mean": fmt_optional(contrast.a_fd_mean),
                "b_fd_mean": fmt_optional(contrast.b_fd_mean),
                "delta_fd_mean": fmt_optional(contrast.delta_fd_mean),
                "a_fd_perc": fmt_optional(contrast.a_fd_perc),
                "b_fd_perc": fmt_optional(contrast.b_fd_perc),
                "delta_fd_perc": fmt_optional(contrast.delta_fd_perc),
                "delta_tsnr_outlier": str(flags["tsnr"]).lower(),
                "delta_fd_mean_outlier": str(flags["fd_mean"]).lower(),
                "delta_fd_perc_outlier": str(flags["fd_perc"]).lower(),
                "n_delta_outliers": str(n_outliers),
                "review": str(not contrast.complete or n_outliers > 0).lower(),
            }
        )

    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=list(output[0]),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(output)
    return output


def write_condition_contrast_bounds(
    path: Path,
    contrasts: list[ContrastIQM],
    bounds: dict[tuple[str, str], tuple[float, float, float, float, float]],
) -> None:
    rows = []
    for contrast, _, _ in CONTRASTS:
        for metric in CONTRAST_METRICS:
            metric_bounds = bounds.get((contrast, metric))
            if metric_bounds is None:
                continue
            n_complete = sum(
                row.contrast == contrast
                and getattr(row, f"delta_{metric}") is not None
                for row in contrasts
            )
            rows.append(
                {
                    "contrast": contrast,
                    "metric": metric,
                    "n_complete": str(n_complete),
                    "q1": fmt(metric_bounds[0]),
                    "q3": fmt(metric_bounds[1]),
                    "iqr": fmt(metric_bounds[2]),
                    "lower_fence": fmt(metric_bounds[3]),
                    "upper_fence": fmt(metric_bounds[4]),
                    "review_rule": "condition A minus condition B outside fences",
                }
            )
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def write_subject_report(
    path: Path,
    subjects: list[SubjectIQM],
    tsnr_lower: float,
    fd_upper: float,
    fd_perc_upper: float,
    expected_runs: int,
    fd_threshold: float,
    fd_perc_threshold: float,
    tsnr_threshold: float,
) -> list[dict[str, str]]:
    output = []
    for subject in subjects:
        incomplete_runs = subject.n_runs != expected_runs
        low_tsnr = subject.mean_tsnr < tsnr_lower
        tsnr_threshold_flag = subject.mean_tsnr < tsnr_threshold
        high_fd = subject.mean_fd_mean > fd_upper
        fd_threshold_flag = subject.mean_fd_mean > fd_threshold
        high_fd_perc = subject.mean_fd_perc > fd_perc_upper
        fd_perc_threshold_flag = subject.mean_fd_perc > fd_perc_threshold
        moderate_fd_perc = subject.mean_fd_perc > 20
        severe_fd_perc = subject.mean_fd_perc > 50
        any_run_severe_fd_perc = subject.max_fd_perc > 50
        review = (
            incomplete_runs
            or low_tsnr
            or tsnr_threshold_flag
            or high_fd
            or fd_threshold_flag
            or high_fd_perc
            or fd_perc_threshold_flag
            or any_run_severe_fd_perc
        )
        output.append(
            {
                "participant": subject.participant,
                "n_runs": str(subject.n_runs),
                "expected_runs": str(expected_runs),
                "mean_tsnr": fmt(subject.mean_tsnr),
                "min_run_tsnr": fmt(subject.min_tsnr),
                "mean_fd_mean": fmt(subject.mean_fd_mean),
                "max_run_fd_mean": fmt(subject.max_fd_mean),
                "total_fd_num": str(subject.total_fd_num),
                "mean_fd_perc": fmt(subject.mean_fd_perc),
                "max_run_fd_perc": fmt(subject.max_fd_perc),
                "incomplete_runs": str(incomplete_runs).lower(),
                "low_mean_tsnr": str(low_tsnr).lower(),
                "mean_tsnr_lt_threshold": str(tsnr_threshold_flag).lower(),
                "high_mean_fd": str(high_fd).lower(),
                "mean_fd_gt_threshold": str(fd_threshold_flag).lower(),
                "high_mean_fd_perc": str(high_fd_perc).lower(),
                "mean_fd_perc_gt_review_threshold": str(
                    fd_perc_threshold_flag
                ).lower(),
                "mean_fd_perc_gt_20": str(moderate_fd_perc).lower(),
                "mean_fd_perc_gt_50": str(severe_fd_perc).lower(),
                "any_run_fd_perc_gt_50": str(any_run_severe_fd_perc).lower(),
                "review": str(review).lower(),
            }
        )

    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=list(output[0]),
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(output)
    return output


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
        "--bidsDir",
        "--bids-dir",
        dest="bids_dir",
        type=Path,
        default=Path(
            os.environ.get("BIDS_DIR", "/ZPOOL/data/projects/r21-cardgame/bids")
        ),
        help="BIDS directory used to read run conditions from events files.",
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
    parser.add_argument(
        "--fd-perc-threshold",
        type=float,
        default=50,
        help=(
            "Review subjects when the mean percentage of volumes above "
            "0.2-mm FD exceeds this value (default: 50)."
        ),
    )
    parser.add_argument(
        "--tsnr-threshold",
        type=float,
        default=30,
        help="Also review subjects with mean tSNR below this value (default: 30).",
    )
    parser.add_argument("--expected-runs", type=int, default=4)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    mriqc_dir = args.mriqc_dir.expanduser().resolve()
    bids_dir = args.bids_dir.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    if not mriqc_dir.is_dir():
        raise SystemExit(f"MRIQC directory not found: {mriqc_dir}")
    if not bids_dir.is_dir():
        raise SystemExit(f"BIDS directory not found: {bids_dir}")
    if args.fd_threshold <= 0:
        raise SystemExit("--fd-threshold must be greater than zero")
    if not 0 < args.fd_perc_threshold <= 100:
        raise SystemExit("--fd-perc-threshold must be between 0 and 100")
    if args.expected_runs <= 0:
        raise SystemExit("--expected-runs must be greater than zero")
    if args.tsnr_threshold <= 0:
        raise SystemExit("--tsnr-threshold must be greater than zero")

    try:
        runs = read_iqms(mriqc_dir, args.task, bids_dir)
        tsnr = tukey_bounds([run.tsnr for run in runs])
        fd_mean = tukey_bounds([run.fd_mean for run in runs])
        subjects = summarize_subjects(runs)
        subject_tsnr = tukey_bounds([subject.mean_tsnr for subject in subjects])
        subject_fd_mean = tukey_bounds(
            [subject.mean_fd_mean for subject in subjects]
        )
        subject_fd_perc = tukey_bounds(
            [subject.mean_fd_perc for subject in subjects]
        )
        condition_contrasts = calculate_condition_contrasts(runs)
        contrast_bounds = condition_contrast_bounds(condition_contrasts)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"ERROR: {error}") from error

    output_dir.mkdir(parents=True, exist_ok=True)
    run_report = output_dir / f"task-{args.task}_mriqc_outliers.tsv"
    bounds_report = output_dir / f"task-{args.task}_mriqc_bounds.tsv"
    subject_report = output_dir / f"task-{args.task}_mriqc_subject_summary.tsv"
    contrast_report = (
        output_dir / f"task-{args.task}_mriqc_condition_contrasts.tsv"
    )
    contrast_bounds_report = (
        output_dir / f"task-{args.task}_mriqc_condition_contrast_bounds.tsv"
    )
    rows = write_run_report(
        run_report,
        runs,
        tsnr[3],
        fd_mean[4],
        args.fd_threshold,
        args.tsnr_threshold,
    )
    subject_rows = write_subject_report(
        subject_report,
        subjects,
        subject_tsnr[3],
        subject_fd_mean[4],
        subject_fd_perc[4],
        args.expected_runs,
        args.fd_threshold,
        args.fd_perc_threshold,
        args.tsnr_threshold,
    )
    contrast_rows = write_condition_contrast_report(
        contrast_report, condition_contrasts, contrast_bounds
    )
    write_condition_contrast_bounds(
        contrast_bounds_report, condition_contrasts, contrast_bounds
    )
    write_bounds(
        bounds_report,
        [
            (
                "run_tsnr",
                tsnr,
                f"value < {fmt(tsnr[3])} or value < {args.tsnr_threshold:g}",
            ),
            (
                "run_fd_mean",
                fd_mean,
                f"value > {fmt(fd_mean[4])} or value > {args.fd_threshold:g}",
            ),
            (
                "subject_mean_tsnr",
                subject_tsnr,
                f"value < {fmt(subject_tsnr[3])} or value < {args.tsnr_threshold:g}",
            ),
            (
                "subject_mean_fd_mean",
                subject_fd_mean,
                f"value > {fmt(subject_fd_mean[4])} or value > {args.fd_threshold:g}",
            ),
            (
                "subject_mean_fd_perc",
                subject_fd_perc,
                f"value > {fmt(subject_fd_perc[4])} or value > {args.fd_perc_threshold:g}",
            ),
        ],
    )

    review_count = sum(row["review"] == "true" for row in rows)
    subject_review_count = sum(row["review"] == "true" for row in subject_rows)
    differential_rows = [
        row
        for row in contrast_rows
        if row["complete"] == "true" and int(row["n_delta_outliers"]) > 0
    ]
    differential_subjects = {row["participant"] for row in differential_rows}
    incomplete_contrast_subjects = {
        row["participant"]
        for row in contrast_rows
        if row["complete"] == "false"
    }
    print(f"Runs reviewed: {len(runs)}")
    print(f"Runs flagged: {review_count}")
    print(f"Subjects reviewed: {len(subjects)}")
    print(f"Subjects flagged: {subject_review_count}")
    print(f"Complete contrast rows with QC outliers: {len(differential_rows)}")
    print(f"Subjects with differential-QC outliers: {len(differential_subjects)}")
    print(
        "Subjects with incomplete condition contrasts: "
        f"{len(incomplete_contrast_subjects)}"
    )
    print(f"Low-tSNR fence: {fmt(tsnr[3])}")
    print(f"High-FD fence: {fmt(fd_mean[4])}; absolute threshold: {args.fd_threshold:g}")
    print(
        "Subject FD-percent review threshold: "
        f"{args.fd_perc_threshold:g}% of volumes above 0.2-mm FD"
    )
    print(f"Wrote {run_report}")
    print(f"Wrote {bounds_report}")
    print(f"Wrote {subject_report}")
    print(f"Wrote {contrast_report}")
    print(f"Wrote {contrast_bounds_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
