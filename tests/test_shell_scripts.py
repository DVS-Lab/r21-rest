from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class ShellScriptTests(unittest.TestCase):
    def test_smoothing_dry_runs_use_expected_input_mask_and_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            derivatives = root / "derivatives"
            func = derivatives / "fmriprep-25.2.5" / "sub-001" / "func"
            func.mkdir(parents=True)
            stem = "sub-001_task-rest_run-01_space-MNI152NLin6Asym_res-native"
            bold = func / f"{stem}_desc-preproc_bold.nii.gz"
            mask = func / f"{stem}_desc-brain_mask.nii.gz"
            bold.touch()
            mask.touch()

            fsldir = derivatives / "fsl"
            fsldir.mkdir()
            (fsldir / "melodic_filelist.txt").write_text(f"{bold}\n")
            env = os.environ | {
                "DERIVATIVES_ROOT": str(derivatives),
                "WORK_ROOT": str(root / "scratch"),
            }

            single = subprocess.run(
                [
                    "bash",
                    str(REPO_ROOT / "code" / "smooth-3dBlurToFWHM.sh"),
                    "001",
                    "01",
                    "--dry-run",
                ],
                env=env,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn(str(mask), single.stderr)
            self.assertIn(f"{stem}_desc-preproc_bold_5mm.nii.gz", single.stderr)

            batch = subprocess.run(
                [
                    "bash",
                    str(REPO_ROOT / "code" / "run_smooth-3dBlurToFWHM.sh"),
                    "--dry-run",
                ],
                env=env,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("Runs: 1", batch.stderr)
            self.assertIn("sub-001", batch.stderr)

    def test_analysis_scripts_render_expected_defaults(self):
        melodic = subprocess.run(
            ["bash", str(REPO_ROOT / "code" / "melodic.sh"), "20", "--dry-run"],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("melodic_filelist_5mm.txt", melodic.stderr)

        smith = subprocess.run(
            [
                "bash",
                str(REPO_ROOT / "code" / "match_smith09.sh"),
                "20",
                "--dry-run",
            ],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("PNAS_Smith09_rsn10.nii.gz", smith.stderr)
        self.assertIn("fslcc -t -1 --noabs", smith.stderr)


if __name__ == "__main__":
    unittest.main()
