#!/usr/bin/env python3
"""Summarize fMRIPrep and MRIQC preprocessing status for R21 participants."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shlex
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


ASSIGNMENT_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")


def strip_shell_comment(line: str) -> str:
    in_single = False
    in_double = False
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\" and in_double:
            escaped = True
            continue
        if char == "'" and not in_double:
            in_single = not in_single
            continue
        if char == '"' and not in_single:
            in_double = not in_double
            continue
        if char == "#" and not in_single and not in_double:
            return line[:index]
    return line


def shell_value(value: str) -> str:
    lexer = shlex.shlex(value, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    parts = list(lexer)
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return " ".join(parts)


def expand_vars(value: str, config: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        name = match.group(1) or match.group(2)
        return config.get(name, os.environ.get(name, ""))

    previous = None
    expanded = value
    for _ in range(10):
        if expanded == previous:
            break
        previous = expanded
        expanded = VAR_RE.sub(replace, expanded)
    return expanded


def parse_shell_config(path: Path) -> dict[str, str]:
    config: dict[str, str] = {}
    for raw_line in path.read_text().splitlines():
        line = strip_shell_comment(raw_line).strip()
        if not line:
            continue
        match = ASSIGNMENT_RE.match(line)
        if not match:
            continue
        key, raw_value = match.groups()
        config[key] = expand_vars(shell_value(raw_value.strip()), config)
    return config


def normalize_participant(label: str) -> str:
    cleaned = label.strip()
    if cleaned.startswith("sub-"):
        cleaned = cleaned[4:]
    if not cleaned:
        raise ValueError("Empty participant label")
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", cleaned):
        raise ValueError(f"Invalid participant label: {label}")
    return f"sub-{cleaned}"


def read_subjects_file(path: Path) -> list[str]:
    subjects = []
    for raw_line in path.read_text().splitlines():
        line = strip_shell_comment(raw_line).strip()
        if line:
            subjects.append(normalize_participant(line))
    return sorted(set(subjects))


def list_bids_subjects(bids_dir: Path) -> list[str]:
    if not bids_dir.is_dir():
        raise FileNotFoundError(f"BIDS directory not found: {bids_dir}")
    subjects = [
        normalize_participant(path.name)
        for path in bids_dir.glob("sub-*")
        if path.is_dir()
    ]
    return sorted(set(subjects))


def marker_state(status_root: Path, tool: str, participant: str) -> str:
    tool_dir = status_root / tool
    for state in ("complete", "running", "failed"):
        if (tool_dir / f"{participant}.{state}").exists():
            return state
    return "missing"


def count_matches(root: Path, patterns: Iterable[str]) -> int:
    if not root.exists():
        return 0
    seen: set[Path] = set()
    for pattern in patterns:
        seen.update(root.rglob(pattern))
    return len(seen)


@dataclass
class ParticipantStatus:
    participant: str
    fmriprep_marker: str
    fmriprep_html: bool
    fmriprep_preproc_bold: int
    fmriprep_confounds: int
    mriqc_marker: str
    mriqc_html: int
    missing: str


def participant_status(config: dict[str, str], participant: str) -> ParticipantStatus:
    task_id = config.get("TASK_ID", "rest")
    status_root = Path(config["STATUS_ROOT"])
    fmriprep_root = Path(config["FMRIPREP_OUTPUT_DIR"])
    mriqc_root = Path(config["MRIQC_OUTPUT_DIR"])

    fmriprep_subject_dir = fmriprep_root / participant
    fmriprep_html = (fmriprep_root / f"{participant}.html").exists()
    preproc_count = count_matches(
        fmriprep_subject_dir,
        [
            f"*_task-{task_id}_*desc-preproc_bold.nii.gz",
            f"*_task-{task_id}_*bold.dtseries.nii",
            f"*_task-{task_id}_*bold.func.gii",
        ],
    )
    confounds_count = count_matches(
        fmriprep_subject_dir,
        [f"*_task-{task_id}_*desc-confounds_timeseries.tsv"],
    )
    mriqc_html = count_matches(mriqc_root, [f"{participant}*.html"])

    missing = []
    if not fmriprep_html:
        missing.append("fmriprep_html")
    if preproc_count == 0:
        missing.append("fmriprep_preproc_bold")
    if confounds_count == 0:
        missing.append("fmriprep_confounds")
    if mriqc_html == 0:
        missing.append("mriqc_html")

    return ParticipantStatus(
        participant=participant,
        fmriprep_marker=marker_state(status_root, "fmriprep", participant),
        fmriprep_html=fmriprep_html,
        fmriprep_preproc_bold=preproc_count,
        fmriprep_confounds=confounds_count,
        mriqc_marker=marker_state(status_root, "mriqc", participant),
        mriqc_html=mriqc_html,
        missing=",".join(missing) if missing else "none",
    )


def format_table(rows: list[ParticipantStatus]) -> str:
    headers = [
        "participant",
        "fmriprep_marker",
        "fmriprep_html",
        "preproc_bold",
        "confounds",
        "mriqc_marker",
        "mriqc_html",
        "missing",
    ]
    body = [
        [
            row.participant,
            row.fmriprep_marker,
            "yes" if row.fmriprep_html else "no",
            str(row.fmriprep_preproc_bold),
            str(row.fmriprep_confounds),
            row.mriqc_marker,
            str(row.mriqc_html),
            row.missing,
        ]
        for row in rows
    ]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in body))
        if body
        else len(headers[index])
        for index in range(len(headers))
    ]
    lines = [
        "  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)),
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
        for row in rows:
            writer.writerow(asdict(row))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize fMRIPrep and MRIQC participant completion."
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Optional shell configuration file. Defaults to config/linux.env, then config/linux.env.example.",
    )
    parser.add_argument("--subjects", type=Path, help="Optional participant list.")
    parser.add_argument("--output-csv", type=Path, help="Optional CSV summary path.")
    parser.add_argument("--output-json", type=Path, help="Optional JSON summary path.")
    parser.add_argument(
        "--fail-on-missing",
        action="store_true",
        help="Exit nonzero if any participant is missing expected outputs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    config_path = args.config
    if config_path is None:
        local_config = repo_root / "config" / "linux.env"
        config_path = local_config if local_config.exists() else repo_root / "config" / "linux.env.example"
    config = parse_shell_config(config_path)
    required = ["BIDS_DIR", "FMRIPREP_OUTPUT_DIR", "MRIQC_OUTPUT_DIR", "STATUS_ROOT"]
    missing_config = [key for key in required if not config.get(key)]
    if missing_config:
        raise SystemExit(f"Missing required config value(s): {', '.join(missing_config)}")

    if args.subjects:
        subjects = read_subjects_file(args.subjects)
    else:
        subjects = list_bids_subjects(Path(config["BIDS_DIR"]))
    if not subjects:
        raise SystemExit("No participants found.")

    rows = [participant_status(config, subject) for subject in subjects]
    print(f"Using config: {config_path}")
    print(format_table(rows))

    if args.output_csv:
        write_csv(args.output_csv, rows)
    if args.output_json:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(json.dumps([asdict(row) for row in rows], indent=2) + "\n")

    if args.fail_on_missing and any(row.missing != "none" for row in rows):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
