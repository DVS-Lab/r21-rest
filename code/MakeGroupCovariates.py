#!/usr/bin/env python3
"""Create task-rest run and contrast covariates for group randomise models."""

from __future__ import annotations

import argparse
import csv
import math
import os
from collections import defaultdict
from pathlib import Path


CONDITIONS = ("sham", "rtpj", "vlpfc", "both")
CONTRASTS: tuple[tuple[str, dict[str, float]], ...] = (
    ("both-minus-sham", {"both": 1.0, "sham": -1.0}),
    ("both-minus-rtpj", {"both": 1.0, "rtpj": -1.0}),
    ("both-minus-vlpfc", {"both": 1.0, "vlpfc": -1.0}),
    ("rtpj-minus-vlpfc", {"rtpj": 1.0, "vlpfc": -1.0}),
    ("rtpj-minus-sham", {"rtpj": 1.0, "sham": -1.0}),
    ("vlpfc-minus-sham", {"vlpfc": 1.0, "sham": -1.0}),
    (
        "both-minus-mean-rtpj-vlpfc",
        {"both": 1.0, "rtpj": -0.5, "vlpfc": -0.5},
    ),
)
RUN_FIELDS = (
    "participant",
    "run",
    "condition",
    "condition_source",
    "tsnr",
    "fd_mean",
    "mean_pupil_area",
    "blink_rate_per_min",
    "total_blinks",
    "eye_closed_fraction",
    "n_event_rows",
    "event_duration_s",
    "events",
    "mriqc_json",
)
CONTRAST_FIELDS = (
    "participant",
    "contrast",
    "complete",
    "missing_conditions",
    "delta_tsnr",
    "delta_fd_mean",
    "delta_mean_pupil_area",
    "delta_blink_rate_per_min",
    "delta_total_blinks",
    "delta_eye_closed_fraction",
)


def fmt(value: float | None) -> str:
    if value is None or not math.isfinite(value):
        return "n/a"
    return f"{value:.10g}"


def parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    stripped = value.strip()
    if stripped == "" or stripped.lower() in {"n/a", "nan", "none"}:
        return None
    try:
        number = float(stripped)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def normalize_condition(value: str | None) -> str | None:
    if value is None:
        return None
    condition = value.strip().lower()
    if condition == "":
        return None
    if condition == "sham":
        return "sham"
    if condition in {"rtpj", "right-tpj", "right_tpj"}:
        return "rtpj"
    if condition in {"vlpfc", "vlpfc-left", "left-vlpfc", "left_vlpfc"}:
        return "vlpfc"
    if condition == "both":
        return "both"
    return None


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def weighted_mean(values: list[tuple[float, float]]) -> float | None:
    if not values:
        return None
    weight_sum = sum(weight for _value, weight in values)
    if weight_sum <= 0:
        return sum(value for value, _weight in values) / len(values)
    return sum(value * weight for value, weight in values) / weight_sum


def summarize_events(path: Path) -> dict[str, object]:
    summary: dict[str, object] = {
        "condition": None,
        "mean_pupil_area": None,
        "blink_rate_per_min": None,
        "total_blinks": None,
        "eye_closed_fraction": None,
        "n_event_rows": 0,
        "event_duration_s": None,
    }
    if not path.is_file():
        return summary

    rows = read_tsv(path)
    summary["n_event_rows"] = len(rows)
    if not rows:
        return summary

    conditions = {
        condition
        for row in rows
        for condition in (
            normalize_condition(row.get("trial_type")),
            normalize_condition(row.get("target")),
        )
        if condition is not None
    }
    if len(conditions) == 1:
        summary["condition"] = next(iter(conditions))
    elif len(conditions) > 1:
        raise ValueError(f"{path}: expected one resting condition; found {sorted(conditions)}")

    durations = [parse_float(row.get("duration")) or 0.0 for row in rows]
    total_duration = sum(durations)
    summary["event_duration_s"] = total_duration if total_duration > 0 else None

    pupil_values: list[tuple[float, float]] = []
    eye_closed_values: list[tuple[float, float]] = []
    total_blinks = 0.0
    has_blinks = False
    for row, duration in zip(rows, durations):
        weight = duration if duration > 0 else 1.0
        pupil = parse_float(row.get("meanPupilArea"))
        if pupil is not None:
            pupil_values.append((pupil, weight))
        eye_closed = parse_float(row.get("eyeClosed"))
        if eye_closed is not None:
            eye_closed_values.append((eye_closed, weight))
        blinks = parse_float(row.get("nrBlinks"))
        if blinks is not None:
            total_blinks += blinks
            has_blinks = True

    summary["mean_pupil_area"] = weighted_mean(pupil_values)
    summary["eye_closed_fraction"] = weighted_mean(eye_closed_values)
    if has_blinks:
        summary["total_blinks"] = total_blinks
        if total_duration > 0:
            summary["blink_rate_per_min"] = total_blinks / total_duration * 60.0
    return summary


def default_bids_dir() -> Path:
    if os.environ.get("BIDS_DIR"):
        return Path(os.environ["BIDS_DIR"])
    for candidate in (
        Path("/ZPOOL/data/projects/r21-cardgame/bids"),
        Path("/Users/tug87422/github/r21-cardgame/bids"),
    ):
        if candidate.exists():
            return candidate
    return Path("/ZPOOL/data/projects/r21-cardgame/bids")


def bids_events_path(bids_dir: Path, participant: str, task: str, run: str) -> Path:
    return (
        bids_dir
        / participant
        / "func"
        / f"{participant}_task-{task}_run-{int(run):02d}_events.tsv"
    )


def build_run_rows(mriqc_path: Path, bids_dir: Path, task: str) -> list[dict[str, str]]:
    rows = read_tsv(mriqc_path)
    if not rows:
        raise ValueError(f"{mriqc_path} has no rows")
    required = {"participant", "run", "tsnr", "fd_mean", "source"}
    missing = required.difference(rows[0])
    if missing:
        raise ValueError(f"{mriqc_path} is missing columns: {sorted(missing)}")

    output: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for row in rows:
        participant = row["participant"].strip()
        run = f"{int(row['run']):02d}"
        key = (participant, run)
        if key in seen:
            raise ValueError(f"Duplicate MRIQC row for {participant} run-{run}")
        seen.add(key)

        events = bids_events_path(bids_dir, participant, task, run)
        event_summary = summarize_events(events)
        mriqc_condition = normalize_condition(row.get("condition"))
        event_condition = event_summary["condition"]
        if (
            mriqc_condition is not None
            and event_condition is not None
            and mriqc_condition != event_condition
        ):
            raise ValueError(
                f"{participant} run-{run}: MRIQC condition {mriqc_condition} "
                f"does not match events condition {event_condition}"
            )
        condition = mriqc_condition or event_condition
        if mriqc_condition:
            condition_source = "mriqc"
        elif event_condition:
            condition_source = "events"
        else:
            condition_source = "missing"

        output.append(
            {
                "participant": participant,
                "run": run,
                "condition": condition or "n/a",
                "condition_source": condition_source,
                "tsnr": fmt(parse_float(row["tsnr"])),
                "fd_mean": fmt(parse_float(row["fd_mean"])),
                "mean_pupil_area": fmt(event_summary["mean_pupil_area"]),  # type: ignore[arg-type]
                "blink_rate_per_min": fmt(event_summary["blink_rate_per_min"]),  # type: ignore[arg-type]
                "total_blinks": fmt(event_summary["total_blinks"]),  # type: ignore[arg-type]
                "eye_closed_fraction": fmt(event_summary["eye_closed_fraction"]),  # type: ignore[arg-type]
                "n_event_rows": str(event_summary["n_event_rows"]),
                "event_duration_s": fmt(event_summary["event_duration_s"]),  # type: ignore[arg-type]
                "events": str(events),
                "mriqc_json": row["source"],
            }
        )
    return output


def contrast_value(
    profile: dict[str, dict[str, str]], weights: dict[str, float], metric: str
) -> float | None:
    total = 0.0
    for condition, weight in weights.items():
        value = parse_float(profile[condition][metric])
        if value is None:
            return None
        total += value * weight
    return total


def build_contrast_rows(run_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    profiles: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    for row in run_rows:
        condition = normalize_condition(row["condition"])
        if condition is None:
            continue
        participant = row["participant"]
        if condition in profiles[participant]:
            raise ValueError(f"Duplicate {condition} run for {participant}")
        profiles[participant][condition] = row

    output: list[dict[str, str]] = []
    for participant in sorted(profiles):
        profile = profiles[participant]
        for contrast, weights in CONTRASTS:
            missing = [condition for condition in weights if condition not in profile]
            complete = not missing
            row = {
                "participant": participant,
                "contrast": contrast,
                "complete": str(complete).lower(),
                "missing_conditions": ",".join(missing),
            }
            for metric in (
                "tsnr",
                "fd_mean",
                "mean_pupil_area",
                "blink_rate_per_min",
                "total_blinks",
                "eye_closed_fraction",
            ):
                row[f"delta_{metric}"] = (
                    fmt(contrast_value(profile, weights, metric)) if complete else "n/a"
                )
            output.append(row)
    return output


def write_tsv(path: Path, rows: list[dict[str, str]], fieldnames: tuple[str, ...]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=fieldnames, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    qc_dir = repo_root / "derivatives" / "qc"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", default="rest")
    parser.add_argument(
        "--mriqc-runs",
        type=Path,
        default=qc_dir / "task-rest_mriqc_outliers.tsv",
        help="Run-level MRIQC table from OutlierID.py.",
    )
    parser.add_argument(
        "--bids-dir",
        type=Path,
        default=default_bids_dir(),
        help="BIDS directory containing task-rest events TSV files.",
    )
    parser.add_argument(
        "--run-output",
        type=Path,
        default=qc_dir / "task-rest_run_covariates.tsv",
    )
    parser.add_argument(
        "--contrast-output",
        type=Path,
        default=qc_dir / "task-rest_group_covariates.tsv",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    run_rows = build_run_rows(args.mriqc_runs.resolve(), args.bids_dir.resolve(), args.task)
    contrast_rows = build_contrast_rows(run_rows)
    write_tsv(args.run_output.resolve(), run_rows, RUN_FIELDS)
    write_tsv(args.contrast_output.resolve(), contrast_rows, CONTRAST_FIELDS)
    complete = sum(row["complete"] == "true" for row in contrast_rows)
    print(f"Runs summarized: {len(run_rows)}")
    print(f"Condition contrasts summarized: {len(contrast_rows)}")
    print(f"Complete condition contrasts: {complete}/{len(contrast_rows)}")
    print(f"Wrote {args.run_output.resolve()}")
    print(f"Wrote {args.contrast_output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
