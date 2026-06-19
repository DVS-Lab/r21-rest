from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "code" / "check_preprocessing_status.py"
SPEC = importlib.util.spec_from_file_location("check_preprocessing_status", MODULE_PATH)
status = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = status
SPEC.loader.exec_module(status)


def touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("ok\n")


class PreprocessingStatusTests(unittest.TestCase):
    def test_read_subjects_normalizes_comments_and_sorts(self):
        fixture = Path(__file__).resolve().parent / "fixtures" / "subjects.txt"
        self.assertEqual(status.read_subjects(fixture), ["sub-001", "sub-002"])

    def test_list_bids_subjects_keeps_only_requested_task(self):
        with tempfile.TemporaryDirectory() as tmp:
            bids = Path(tmp) / "bids"
            touch(bids / "sub-001" / "func" / "sub-001_task-rest_run-01_bold.json")
            touch(
                bids
                / "sub-002"
                / "func"
                / "sub-002_task-cardgame_run-01_bold.json"
            )
            self.assertEqual(status.list_bids_subjects(bids, "rest"), ["sub-001"])

    def test_complete_participant_and_group_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bids = root / "bids"
            fmriprep = root / "fmriprep"
            mriqc = root / "mriqc"
            freesurfer = root / "freesurfer"
            participant = "sub-001"
            bold_stems = [
                "sub-001_task-rest_run-01",
                "sub-001_task-rest_run-02",
            ]

            touch(bids / participant / "anat" / "sub-001_T1w.json")
            for stem in bold_stems:
                touch(bids / participant / "func" / f"{stem}_bold.json")
                touch(
                    fmriprep
                    / participant
                    / "func"
                    / f"{stem}_space-MNI152NLin6Asym_desc-preproc_bold.nii.gz"
                )
                touch(
                    fmriprep
                    / participant
                    / "func"
                    / f"{stem}_space-fsLR_den-91k_bold.dtseries.nii"
                )
                touch(
                    fmriprep
                    / participant
                    / "func"
                    / f"{stem}_desc-confounds_timeseries.tsv"
                )
                touch(mriqc / "reports" / f"{stem}_bold.html")
                touch(mriqc / "derivatives" / participant / "func" / f"{stem}_bold.json")

            touch(fmriprep / f"{participant}.html")
            touch(fmriprep / participant / "anat" / "sub-001_desc-preproc_T1w.nii.gz")
            touch(freesurfer / participant / "scripts" / "recon-all.done")
            touch(mriqc / "reports" / "sub-001_T1w.html")
            touch(mriqc / "derivatives" / participant / "anat" / "sub-001_T1w.json")
            for group_file in ("bold.csv", "T1w.csv", "group_bold.html", "group_T1w.html"):
                touch(mriqc / group_file)

            row = status.participant_status(
                bids, fmriprep, mriqc, freesurfer, participant
            )
            self.assertTrue(row.complete)
            self.assertEqual(row.expected_bold, 2)
            self.assertEqual(row.fmriprep_mni_bold, 2)
            self.assertEqual(row.fmriprep_cifti_bold, 2)
            self.assertEqual(row.fmriprep_confounds, 2)
            self.assertEqual(row.mriqc_bold_reports, 2)
            self.assertEqual(row.missing, "none")
            self.assertTrue(status.mriqc_group_status(mriqc).complete)

    def test_missing_outputs_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bids = root / "bids"
            participant = "sub-002"
            touch(bids / participant / "anat" / "sub-002_T1w.json")
            touch(
                bids
                / participant
                / "func"
                / "sub-002_task-rest_run-01_bold.json"
            )

            row = status.participant_status(
                bids,
                root / "fmriprep",
                root / "mriqc",
                root / "freesurfer",
                participant,
            )
            self.assertFalse(row.complete)
            self.assertIn("fmriprep_report", row.missing)
            self.assertIn("fmriprep_mni=0/1", row.missing)
            self.assertIn("mriqc_bold_reports=0/1", row.missing)


if __name__ == "__main__":
    unittest.main()
