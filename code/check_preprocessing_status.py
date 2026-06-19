#!/usr/bin/env python3
"""Verify core fMRIPrep and MRIQC outputs against the source BIDS dataset."""

from __future__ import annotations

import argparse
import csv
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path


def normalize_subject(label: str) -> str:
    label = label.strip()
    if not label.startswith("sub-"):
        label = f"sub-{label}"
    if not re.fullmatch(r"sub-[A-Za-z0-9][A-Za-z0-9._-]*", label):
        raise ValueError(f"Invalid participant label: {label}")
    return label


def read_subjects(path: Path) -> list[str]:
    subjects = set()
    for raw_line in path.read_text().splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if line:
            subjects.add(normalize_subject(line))
    return sorted(subjects)


def list_bids_subjects(bids_dir: Path, task: str) -> list[str]:
    return sorted(
        path.name
        for path in bids_dir.glob("sub-*")
        if path.is_dir() and expected_bold_stems(bids_dir, path.name, task)
    )


def remove_suffix(name: str, suffixes: tuple[str, ...]) -> str | None:
    for suffix in suffixes:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return None


def expected_bold_stems(bids_dir: Path, participant: str, task: str) -> list[str]:
    subject_dir = bids_dir / participant
    stems = set()
    patterns = (
        f"{participant}*_task-{task}_*_bold.json",
        f"{participant}*_task-{task}_*_bold.nii.gz",
        f"{participant}*_task-{task}_*_bold.nii",
    )
    for pattern in patterns:
        for path in subject_dir.rglob(pattern):
            stem = remove_suffix(path.name, ("_bold.json", "_bold.nii.gz", "_bold.nii"))
            if stem:
                stems.add(stem)
    return sorted(stems)


def expected_t1w_stems(bids_dir: Path, participant: str) -> list[str]:
    subject_dir = bids_dir / participant
    stems = set()
    for pattern in (f"{participant}*_T1w.json", f"{participant}*_T1w.nii.gz"):
        for path in subject_dir.rglob(pattern):
            stem = remove_suffix(path.name, ("_T1w.json", "_T1w.nii.gz"))
            if stem:
                stems.add(stem)
    return sorted(stems)


def nonempty_matches(root: Path, pattern: str) -> list[Path]:
    if not root.exists():
        return []
    matches = []
    for path in root.rglob(pattern):
        try:
            if path.is_file() and path.stat().st_size > 0:
                matches.append(path)
        except OSError:
            continue
    return matches


def has_output(root: Path, pattern: str) -> bool:
    return bool(nonempty_matches(root, pattern))


def coverage(root: Path, stems: list[str], pattern: str) -> int:
    return sum(has_output(root, pattern.format(stem=stem)) for stem in stems)


def ratio(actual: int, expected: int) -> str:
    return f"{actual}/{expected}"


@dataclass
class ParticipantStatus:
    participant: str
    expected_bold: int
    expected_t1w: int
    fmriprep_report: bool
    fmriprep_mni_bold: int
    fmriprep_cifti_bold: int
    fmriprep_confounds: int
    fmriprep_t1w: int
    freesurfer_complete: bool
    mriqc_bold_reports: int
    mriqc_bold_iqms: int
    mriqc_t1w_reports: int
    mriqc_t1w_iqms: int
    complete: bool
    missing: str


def participant_status(
    bids_dir: Path,
    fmriprep_dir: Path,
    mriqc_dir: Path,
    freesurfer_dir: Path,
    participant: str,
    task: str = "rest",
    space: str = "MNI152NLin6Asym",
    cifti_density: str = "91k",
) -> ParticipantStatus:
    bold_stems = expected_bold_stems(bids_dir, participant, task)
    t1w_stems = expected_t1w_stems(bids_dir, participant)
    expected_bold = len(bold_stems)
    expected_t1w = len(t1w_stems)
    fmriprep_subject = fmriprep_dir / participant

    fmriprep_report = has_output(fmriprep_dir, f"{participant}.html")
    mni_bold = coverage(
        fmriprep_subject,
        bold_stems,
        f"{{stem}}_space-{space}*_desc-preproc_bold.nii.gz",
    )
    cifti_bold = coverage(
        fmriprep_subject,
        bold_stems,
        f"{{stem}}_space-fsLR_den-{cifti_density}_bold.dtseries.nii",
    )
    confounds = coverage(
        fmriprep_subject, bold_stems, "{stem}_desc-confounds_timeseries.tsv"
    )
    fmriprep_t1w = coverage(
        fmriprep_subject, t1w_stems, "{stem}*_desc-preproc_T1w.nii.gz"
    )
    freesurfer_complete = has_output(
        freesurfer_dir / participant / "scripts", "recon-all.done"
    )

    mriqc_bold_reports = coverage(mriqc_dir, bold_stems, "{stem}_bold.html")
    mriqc_bold_iqms = coverage(mriqc_dir, bold_stems, "{stem}_bold.json")
    mriqc_t1w_reports = coverage(mriqc_dir, t1w_stems, "{stem}_T1w.html")
    mriqc_t1w_iqms = coverage(mriqc_dir, t1w_stems, "{stem}_T1w.json")

    missing = []
    if expected_bold == 0:
        missing.append("bids_bold=0")
    if expected_t1w == 0:
        missing.append("bids_T1w=0")
    if not fmriprep_report:
        missing.append("fmriprep_report")
    for label, actual, expected in (
        ("fmriprep_mni", mni_bold, expected_bold),
        ("fmriprep_cifti", cifti_bold, expected_bold),
        ("fmriprep_confounds", confounds, expected_bold),
        ("fmriprep_T1w", fmriprep_t1w, expected_t1w),
        ("mriqc_bold_reports", mriqc_bold_reports, expected_bold),
        ("mriqc_bold_iqms", mriqc_bold_iqms, expected_bold),
        ("mriqc_T1w_reports", mriqc_t1w_reports, expected_t1w),
        ("mriqc_T1w_iqms", mriqc_t1w_iqms, expected_t1w),
    ):
        if actual != expected:
            missing.append(f"{label}={actual}/{expected}")
    if not freesurfer_complete:
        missing.append("freesurfer")

    return ParticipantStatus(
        participant=participant,
        expected_bold=expected_bold,
        expected_t1w=expected_t1w,
        fmriprep_report=fmriprep_report,
        fmriprep_mni_bold=mni_bold,
        fmriprep_cifti_bold=cifti_bold,
        fmriprep_confounds=confounds,
        fmriprep_t1w=fmriprep_t1w,
        freesurfer_complete=freesurfer_complete,
        mriqc_bold_reports=mriqc_bold_reports,
        mriqc_bold_iqms=mriqc_bold_iqms,
        mriqc_t1w_reports=mriqc_t1w_reports,
        mriqc_t1w_iqms=mriqc_t1w_iqms,
        complete=not missing,
        missing=",".join(missing) if missing else "none",
    )


@dataclass
class MRIQCGroupStatus:
    bold_csv: bool
    t1w_csv: bool
    bold_report: bool
    t1w_report: bool

    @property
    def complete(self) -> bool:
        return self.bold_csv and self.t1w_csv and self.bold_report and self.t1w_report


def mriqc_group_status(mriqc_dir: Path) -> MRIQCGroupStatus:
    return MRIQCGroupStatus(
        bold_csv=has_output(mriqc_dir, "bold.csv"),
        t1w_csv=has_output(mriqc_dir, "T1w.csv"),
        bold_report=has_output(mriqc_dir, "group_bold.html"),
        t1w_report=has_output(mriqc_dir, "group_T1w.html"),
    )


def format_table(rows: list[ParticipantStatus]) -> str:
    headers = [
        "subject",
        "runs",
        "fprep",
        "MNI",
        "CIFTI",
        "confounds",
        "T1w",
        "FS",
        "MQC reports",
        "MQC IQMs",
        "status",
    ]
    body = []
    for row in rows:
        body.append(
            [
                row.participant,
                str(row.expected_bold),
                "yes" if row.fmriprep_report else "no",
                ratio(row.fmriprep_mni_bold, row.expected_bold),
                ratio(row.fmriprep_cifti_bold, row.expected_bold),
                ratio(row.fmriprep_confounds, row.expected_bold),
                ratio(row.fmriprep_t1w, row.expected_t1w),
                "yes" if row.freesurfer_complete else "no",
                ratio(
                    row.mriqc_bold_reports + row.mriqc_t1w_reports,
                    row.expected_bold + row.expected_t1w,
                ),
                ratio(
                    row.mriqc_bold_iqms + row.mriqc_t1w_iqms,
                    row.expected_bold + row.expected_t1w,
                ),
                "complete" if row.complete else "incomplete",
            ]
        )
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in body))
        for index in range(len(headers))
    ]
    lines = [
        "  ".join(value.ljust(widths[index]) for index, value in enumerate(headers)),
        "  ".join("-" * width for width in widths),
    ]
    lines.extend(
        "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))
        for row in body
    )
    return "\n".join(lines)


def write_csv(path: Path, rows: list[ParticipantStatus]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(asdict(rows[0]).keys()))
        writer.writeheader()
        writer.writerows(asdict(row) for row in rows)


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    derivatives = Path(os.environ.get("DERIVATIVES_ROOT", repo_root / "derivatives"))
    parser = argparse.ArgumentParser(
        description="Verify core fMRIPrep and MRIQC outputs against BIDS inputs."
    )
    parser.add_argument(
        "--bids-dir",
        type=Path,
        default=Path(os.environ.get("BIDS_DIR", "/ZPOOL/data/projects/r21-cardgame/bids")),
    )
    parser.add_argument(
        "--fmriprep-dir",
        type=Path,
        default=Path(
            os.environ.get("FMRIPREP_OUTPUT_DIR", derivatives / "fmriprep-25.2.5")
        ),
    )
    parser.add_argument(
        "--mriqc-dir",
        type=Path,
        default=Path(os.environ.get("MRIQC_OUTPUT_DIR", derivatives / "mriqc")),
    )
    parser.add_argument(
        "--freesurfer-dir",
        type=Path,
        default=Path(os.environ.get("FS_SUBJECTS_DIR", derivatives / "freesurfer")),
    )
    parser.add_argument("--subjects", type=Path)
    parser.add_argument("--task", default=os.environ.get("TASK_ID", "rest"))
    parser.add_argument(
        "--space", default=os.environ.get("FMRIPREP_VOLUME_SPACE", "MNI152NLin6Asym")
    )
    parser.add_argument(
        "--cifti-density", default=os.environ.get("CIFTI_DENSITY", "91k")
    )
    parser.add_argument("--output-csv", type=Path)
    parser.add_argument("--fail-on-missing", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    bids_dir = args.bids_dir.expanduser().resolve()
    if not bids_dir.is_dir():
        raise SystemExit(f"BIDS directory not found: {bids_dir}")

    subjects_file = args.subjects
    default_subjects = repo_root / "code" / "sublist.txt"
    if subjects_file is None and default_subjects.exists():
        subjects_file = default_subjects
    subjects = (
        read_subjects(subjects_file)
        if subjects_file
        else list_bids_subjects(bids_dir, args.task)
    )
    if not subjects:
        raise SystemExit("No participants found.")

    rows = [
        participant_status(
            bids_dir,
            args.fmriprep_dir,
            args.mriqc_dir,
            args.freesurfer_dir,
            subject,
            args.task,
            args.space,
            args.cifti_density,
        )
        for subject in subjects
    ]
    print(format_table(rows))
    complete = sum(row.complete for row in rows)
    print(f"\nParticipants complete: {complete}/{len(rows)}")
    incomplete = [row for row in rows if not row.complete]
    if incomplete:
        print("Missing outputs:")
        for row in incomplete:
            print(f"  {row.participant}: {row.missing}")

    group = mriqc_group_status(args.mriqc_dir)
    print(
        "MRIQC group outputs: "
        f"bold.csv={'yes' if group.bold_csv else 'no'}, "
        f"T1w.csv={'yes' if group.t1w_csv else 'no'}, "
        f"group_bold.html={'yes' if group.bold_report else 'no'}, "
        f"group_T1w.html={'yes' if group.t1w_report else 'no'}"
    )

    if args.output_csv:
        write_csv(args.output_csv, rows)
    if args.fail_on_missing and (complete != len(rows) or not group.complete):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
