from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "code" / "check_preprocessing_status.py"
SPEC = importlib.util.spec_from_file_location("check_preprocessing_status", MODULE_PATH)
status = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = status
SPEC.loader.exec_module(status)


def test_parse_shell_config_expands_prior_values(tmp_path, monkeypatch):
    monkeypatch.setenv("USER", "analyst")
    config = tmp_path / "linux.env"
    config.write_text(
        "\n".join(
            [
                'DERIVATIVES_ROOT="/derivatives/r21-rest"',
                'FMRIPREP_OUTPUT_DIR="${DERIVATIVES_ROOT}/fmriprep-25.2.5"',
                'WORK_ROOT="/scratch/${USER}/r21-rest"',
                'MRIQC_MODALITIES="T1w bold"',
            ]
        )
    )

    parsed = status.parse_shell_config(config)

    assert parsed["FMRIPREP_OUTPUT_DIR"] == "/derivatives/r21-rest/fmriprep-25.2.5"
    assert parsed["WORK_ROOT"] == "/scratch/analyst/r21-rest"
    assert parsed["MRIQC_MODALITIES"] == "T1w bold"


def test_normalize_participant_accepts_prefixed_and_unprefixed_labels():
    assert status.normalize_participant("189") == "sub-189"
    assert status.normalize_participant("sub-189") == "sub-189"


def test_read_subjects_file_uses_comments_and_sorts_fixture():
    fixture = Path(__file__).resolve().parent / "fixtures" / "subjects.txt"

    assert status.read_subjects_file(fixture) == ["sub-001", "sub-002"]


def test_participant_status_detects_expected_outputs(tmp_path):
    fmriprep_root = tmp_path / "derivatives" / "fmriprep"
    mriqc_root = tmp_path / "derivatives" / "mriqc"
    status_root = tmp_path / "derivatives" / "status"
    func_dir = fmriprep_root / "sub-001" / "func"
    func_dir.mkdir(parents=True)
    mriqc_root.mkdir(parents=True)
    (status_root / "fmriprep").mkdir(parents=True)
    (status_root / "mriqc").mkdir(parents=True)

    (fmriprep_root / "sub-001.html").write_text("ok")
    (func_dir / "sub-001_task-rest_space-MNI152NLin2009cAsym_desc-preproc_bold.nii.gz").write_text("ok")
    (func_dir / "sub-001_task-rest_desc-confounds_timeseries.tsv").write_text("ok")
    (mriqc_root / "sub-001_task-rest_bold.html").write_text("ok")
    (status_root / "fmriprep" / "sub-001.complete").write_text("STATE=complete\n")
    (status_root / "mriqc" / "sub-001.complete").write_text("STATE=complete\n")

    row = status.participant_status(
        {
            "TASK_ID": "rest",
            "STATUS_ROOT": str(status_root),
            "FMRIPREP_OUTPUT_DIR": str(fmriprep_root),
            "MRIQC_OUTPUT_DIR": str(mriqc_root),
        },
        "sub-001",
    )

    assert row.fmriprep_marker == "complete"
    assert row.fmriprep_html is True
    assert row.fmriprep_preproc_bold == 1
    assert row.fmriprep_confounds == 1
    assert row.mriqc_marker == "complete"
    assert row.mriqc_html == 1
    assert row.missing == "none"


def test_participant_status_reports_missing_outputs(tmp_path):
    fmriprep_root = tmp_path / "derivatives" / "fmriprep"
    mriqc_root = tmp_path / "derivatives" / "mriqc"
    status_root = tmp_path / "derivatives" / "status"
    fmriprep_root.mkdir(parents=True)
    mriqc_root.mkdir(parents=True)
    status_root.mkdir(parents=True)

    row = status.participant_status(
        {
            "TASK_ID": "rest",
            "STATUS_ROOT": str(status_root),
            "FMRIPREP_OUTPUT_DIR": str(fmriprep_root),
            "MRIQC_OUTPUT_DIR": str(mriqc_root),
        },
        "sub-002",
    )

    assert row.fmriprep_marker == "missing"
    assert "fmriprep_html" in row.missing
    assert "fmriprep_preproc_bold" in row.missing
    assert "mriqc_html" in row.missing
