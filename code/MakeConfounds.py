#!/usr/bin/env python3
"""Extract the lab-standard fMRIPrep confounds for FSL.

Adapted from MakeConfounds.py in the lab's existing repositories. The script
also writes parallel image and confound lists for MELODIC and dual_regression.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path


CONFOUND_SUFFIX = "_desc-confounds_timeseries.tsv"
MOTION = ["trans_x", "trans_y", "trans_z", "rot_x", "rot_y", "rot_z"]
ACOMPCOR = [f"a_comp_cor_{index:02d}" for index in range(6)]
REQUIRED = MOTION + ACOMPCOR + ["framewise_displacement"]
MISSING_VALUES = {"", "n/a", "nan", "na"}
CONDITION_ORDER = {"sham": 1, "rtpj": 2, "vlpfc": 3, "both": 4}


@dataclass(frozen=True)
class RunFiles:
    source_confounds: Path
    events: Path
    bold: Path
    fsl_confounds: Path
    participant: str
    acquired_run: str
    condition: str
    condition_order: int


def normalize_subject(label: str) -> str:
    label = label.strip()
    if not label.startswith("sub-"):
        label = f"sub-{label}"
    if not re.fullmatch(r"sub-[A-Za-z0-9][A-Za-z0-9._-]*", label):
        raise ValueError(f"Invalid participant label: {label}")
    return label


def read_subjects(path: Path) -> set[str]:
    subjects = set()
    for raw_line in path.read_text().splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if line:
            subjects.add(normalize_subject(line))
    if not subjects:
        raise ValueError(f"No participants found in: {path}")
    return subjects


def subject_from_name(path: Path) -> str:
    match = re.match(r"(sub-[^_]+)", path.name)
    if not match:
        raise ValueError(f"Cannot determine participant from: {path}")
    return match.group(1)


def entity_from_name(path: Path, entity: str) -> str:
    match = re.search(rf"(?:^|_){re.escape(entity)}-([^_]+)", path.name)
    if not match:
        raise ValueError(f"Cannot determine {entity} from: {path}")
    return match.group(1)


def find_events(source: Path, bids_dir: Path) -> Path:
    prefix = source.name.removesuffix(CONFOUND_SUFFIX)
    subject = subject_from_name(source)
    matches = sorted((bids_dir / subject).rglob(f"{prefix}_events.tsv"))
    if len(matches) != 1:
        raise ValueError(
            f"Expected one events file for {source.name}; found {len(matches)}"
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
    if len(conditions) != 1:
        found = ", ".join(sorted(conditions)) if conditions else "none"
        raise ValueError(f"{path}: expected one trial_type; found {found}")
    condition = conditions.pop()
    if condition not in CONDITION_ORDER:
        raise ValueError(
            f"{path}: unknown trial_type {condition}; expected "
            + ", ".join(CONDITION_ORDER)
        )
    return condition


def find_preproc_bold(source: Path, fmriprep_dir: Path, space: str) -> Path:
    prefix = source.name.removesuffix(CONFOUND_SUFFIX)
    subject = subject_from_name(source)
    pattern = f"{prefix}_space-{space}*_desc-preproc_bold.nii.gz"
    matches = sorted((fmriprep_dir / subject).rglob(pattern))
    if len(matches) != 1:
        raise ValueError(
            f"Expected one {space} preprocessed BOLD for {source.name}; "
            f"found {len(matches)}"
        )
    return matches[0]


def confound_columns(fieldnames: list[str], source: Path) -> list[str]:
    missing = [name for name in REQUIRED if name not in fieldnames]
    if missing:
        raise ValueError(f"{source}: missing columns: {', '.join(missing)}")

    cosine = [name for name in fieldnames if name.startswith("cosine")]
    nonsteady = [
        name for name in fieldnames if name.startswith("non_steady_state")
    ]
    return cosine + nonsteady + MOTION + ACOMPCOR + ["framewise_displacement"]


def numeric_value(value: str | None, source: Path, row: int, column: str) -> str:
    cleaned = (value or "").strip()
    if cleaned.lower() in MISSING_VALUES:
        return "0"
    try:
        float(cleaned)
    except ValueError as error:
        raise ValueError(
            f"{source}: nonnumeric value in row {row}, column {column}: {cleaned}"
        ) from error
    return cleaned


def extract_confounds(source: Path, output: Path) -> list[str]:
    with source.open(newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if reader.fieldnames is None:
            raise ValueError(f"Confounds file has no header: {source}")
        columns = confound_columns(reader.fieldnames, source)
        rows = list(reader)

    if not rows:
        raise ValueError(f"Confounds file has no data rows: {source}")

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        for row_number, row in enumerate(rows, start=2):
            writer.writerow(
                numeric_value(row.get(column), source, row_number, column)
                for column in columns
            )
    return columns


def find_runs(
    bids_dir: Path,
    fmriprep_dir: Path,
    output_dir: Path,
    task: str,
    space: str,
    subjects: set[str] | None,
) -> list[RunFiles]:
    sources = sorted(
        fmriprep_dir.glob(f"sub-*/**/*_task-{task}_*{CONFOUND_SUFFIX}")
    )
    if subjects is not None:
        sources = [
            source for source in sources if subject_from_name(source) in subjects
        ]
        found_subjects = {subject_from_name(source) for source in sources}
        missing_subjects = sorted(subjects - found_subjects)
        if missing_subjects:
            raise ValueError(
                "No fMRIPrep confounds found for: " + ", ".join(missing_subjects)
            )
    if not sources:
        raise ValueError(f"No task-{task} fMRIPrep confounds found in: {fmriprep_dir}")

    runs = []
    for source in sources:
        subject = subject_from_name(source)
        events = find_events(source, bids_dir)
        condition = condition_from_events(events)
        acquired_run = entity_from_name(source, "run")
        output_name = (
            source.name.removesuffix(CONFOUND_SUFFIX)
            + f"_condition-{condition}_desc-fslConfounds.tsv"
        )
        runs.append(
            RunFiles(
                source_confounds=source,
                events=events,
                bold=find_preproc_bold(source, fmriprep_dir, space),
                fsl_confounds=output_dir / subject / output_name,
                participant=subject,
                acquired_run=acquired_run,
                condition=condition,
                condition_order=CONDITION_ORDER[condition],
            )
        )
    return sorted(
        runs,
        key=lambda run: (run.participant, run.condition_order, run.acquired_run),
    )


def validate_condition_sets(runs: list[RunFiles]) -> None:
    by_subject: dict[str, list[RunFiles]] = {}
    for run in runs:
        by_subject.setdefault(run.participant, []).append(run)

    errors = []
    expected = set(CONDITION_ORDER)
    for participant, participant_runs in sorted(by_subject.items()):
        conditions = [run.condition for run in participant_runs]
        if len(conditions) != len(expected) or set(conditions) != expected:
            found = ", ".join(conditions) if conditions else "none"
            errors.append(
                f"{participant}: expected sham, rtpj, vlpfc, both; found {found}"
            )
    if errors:
        raise ValueError("Incomplete condition sets:\n  " + "\n  ".join(errors))


def find_eligible_runs(
    bids_dir: Path,
    fmriprep_dir: Path,
    output_dir: Path,
    task: str,
    space: str,
    subjects: set[str] | None,
) -> tuple[list[RunFiles], dict[str, str]]:
    sources = sorted(
        fmriprep_dir.glob(f"sub-*/**/*_task-{task}_*{CONFOUND_SUFFIX}")
    )
    available = {subject_from_name(source) for source in sources}
    selected = subjects if subjects is not None else available
    if not selected:
        raise ValueError(f"No task-{task} fMRIPrep confounds found in: {fmriprep_dir}")

    eligible = []
    skipped = {}
    for participant in sorted(selected):
        try:
            participant_runs = find_runs(
                bids_dir,
                fmriprep_dir,
                output_dir,
                task,
                space,
                {participant},
            )
            validate_condition_sets(participant_runs)
        except ValueError as error:
            skipped[participant] = " ".join(str(error).split())
            continue
        eligible.extend(participant_runs)

    if not eligible:
        raise ValueError("No participants have a complete labeled condition set")
    return sorted(
        eligible,
        key=lambda run: (run.participant, run.condition_order, run.acquired_run),
    ), skipped


def write_filelist(path: Path, files: list[Path]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"{file.resolve()}\n" for file in files))


def write_manifest(path: Path, runs: list[RunFiles]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "participant",
        "acquired_run",
        "condition",
        "condition_order",
        "events",
        "bold",
        "confounds",
    ]
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=fieldnames, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        for run in runs:
            writer.writerow(
                {
                    "participant": run.participant,
                    "acquired_run": run.acquired_run,
                    "condition": run.condition,
                    "condition_order": run.condition_order,
                    "events": run.events.resolve(),
                    "bold": run.bold.resolve(),
                    "confounds": run.fsl_confounds.resolve(),
                }
            )


def write_skipped_subjects(path: Path, skipped: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=["participant", "reason"],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for participant, reason in sorted(skipped.items()):
            writer.writerow({"participant": participant, "reason": reason})


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Extract lab-standard fMRIPrep confounds and write FSL file lists."
    )
    parser.add_argument(
        "--bidsDir",
        "--bids-dir",
        dest="bids_dir",
        type=Path,
        default=Path(
            os.environ.get("BIDS_DIR", "/ZPOOL/data/projects/r21-cardgame/bids")
        ),
    )
    parser.add_argument(
        "--fmriprepDir",
        "--fmriprep-dir",
        dest="fmriprep_dir",
        type=Path,
        default=Path(
            os.environ.get(
                "FMRIPREP_OUTPUT_DIR",
                repo_root / "derivatives" / "fmriprep-25.2.5",
            )
        ),
    )
    parser.add_argument(
        "--outDir",
        "--output-dir",
        dest="output_dir",
        type=Path,
        help="Defaults to derivatives/fsl/confounds beside the fMRIPrep directory.",
    )
    parser.add_argument(
        "--subjects",
        type=Path,
        help="Optional participant list. Defaults to code/sublist.txt when present.",
    )
    parser.add_argument("--task", default=os.environ.get("TASK_ID", "rest"))
    parser.add_argument(
        "--space", default=os.environ.get("FMRIPREP_VOLUME_SPACE", "MNI152NLin6Asym")
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    bids_dir = args.bids_dir.expanduser().resolve()
    fmriprep_dir = args.fmriprep_dir.expanduser().resolve()
    if not bids_dir.is_dir():
        raise SystemExit(f"BIDS directory not found: {bids_dir}")
    if not fmriprep_dir.is_dir():
        raise SystemExit(f"fMRIPrep directory not found: {fmriprep_dir}")

    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else fmriprep_dir.parent / "fsl" / "confounds"
    )
    subjects_file = args.subjects
    default_subjects = repo_root / "code" / "sublist.txt"
    if subjects_file is None and default_subjects.exists():
        subjects_file = default_subjects
    try:
        subjects = read_subjects(subjects_file) if subjects_file else None
        runs, skipped = find_eligible_runs(
            bids_dir, fmriprep_dir, output_dir, args.task, args.space, subjects
        )
        for participant, reason in sorted(skipped.items()):
            print(f"WARNING: Skipping {participant}: {reason}", file=sys.stderr)
        for run in runs:
            columns = extract_confounds(run.source_confounds, run.fsl_confounds)
            print(f"Wrote {run.fsl_confounds} ({len(columns)} regressors)")
    except ValueError as error:
        raise SystemExit(f"ERROR: {error}") from error

    fsl_dir = output_dir.parent
    melodic_filelist = fsl_dir / "melodic_filelist.txt"
    confound_filelist = fsl_dir / "confound_filelist.txt"
    manifest = fsl_dir / f"task-{args.task}_run_manifest.tsv"
    skipped_report = fsl_dir / f"task-{args.task}_skipped_subjects.tsv"
    write_filelist(melodic_filelist, [run.bold for run in runs])
    write_filelist(confound_filelist, [run.fsl_confounds for run in runs])
    write_manifest(manifest, runs)
    write_skipped_subjects(skipped_report, skipped)
    participants = {run.participant for run in runs}
    print(f"Included participants: {len(participants)}")
    print(f"Skipped participants: {len(skipped)}")
    print(f"Wrote {melodic_filelist} ({len(runs)} runs)")
    print(f"Wrote {confound_filelist} ({len(runs)} runs)")
    print(f"Wrote {manifest} ({len(runs)} runs)")
    print(f"Wrote {skipped_report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
