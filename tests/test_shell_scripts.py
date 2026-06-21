from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class ShellScriptTests(unittest.TestCase):
    @staticmethod
    def write_command(path: Path, body: str) -> None:
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)

    def test_smoothing_dry_runs_use_expected_input_mask_and_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bids = root / "bids"
            derivatives = root / "derivatives"
            func = derivatives / "fmriprep-25.2.5" / "sub-001" / "func"
            func.mkdir(parents=True)
            stem = "sub-001_task-rest_run-01_space-MNI152NLin6Asym_res-native"
            bold = func / f"{stem}_desc-preproc_bold.nii.gz"
            mask = func / f"{stem}_desc-brain_mask.nii.gz"
            bold.touch()
            mask.touch()
            smoothed = func / f"{stem}_condition-rtpj_order-02_desc-preproc_bold_5mm.nii.gz"
            smoothed.touch()
            confound_file = root / "confounds.tsv"
            confound_file.write_text("0\t0\n0\t0\n")
            events = bids / "sub-001" / "func" / "sub-001_task-rest_run-01_events.tsv"
            events.parent.mkdir(parents=True)
            events.write_text("onset\tduration\ttrial_type\n0\t1\tRTPJ\n")

            fsldir = derivatives / "fsl"
            fsldir.mkdir()
            manifest = fsldir / "task-rest_run_manifest.tsv"
            manifest.write_text(
                "participant\tacquired_run\tcondition\tcondition_order\tevents\tbold\tconfounds\n"
                f"sub-001\t01\trtpj\t2\t{events}\t{bold}\t{confound_file}\n"
            )
            env = os.environ | {
                "BIDS_DIR": str(bids),
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
            self.assertIn("Condition: rtpj (order 02)", single.stderr)
            self.assertIn(
                f"{stem}_condition-rtpj_order-02_desc-preproc_bold_5mm.nii.gz",
                single.stderr,
            )
            self.assertIn("fslmaths", single.stderr)
            self.assertIn("-mas", single.stderr)

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

            regression = subprocess.run(
                [
                    "bash",
                    str(REPO_ROOT / "code" / "regress_confounds.sh"),
                    "001",
                    "01",
                    "--dry-run",
                ],
                env=env,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("3dTproject", regression.stderr)
            self.assertIn("-polort 0", regression.stderr)
            self.assertIn(str(smoothed), regression.stderr)
            self.assertIn("desc-denoised_bold_5mm.nii.gz", regression.stderr)

            regression_batch = subprocess.run(
                [
                    "bash",
                    str(REPO_ROOT / "code" / "run_regress_confounds.sh"),
                    "--dry-run",
                ],
                env=env,
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("Runs: 1", regression_batch.stderr)
            self.assertIn("melodic_filelist_5mm_denoised.txt", regression_batch.stderr)

    def test_analysis_scripts_render_expected_defaults(self):
        melodic = subprocess.run(
            ["bash", str(REPO_ROOT / "code" / "melodic.sh"), "20", "--dry-run"],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("melodic_filelist_5mm_denoised.txt", melodic.stderr)

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
        self.assertIn("smith09_denoised_dim-20", smith.stderr)

        qa = subprocess.run(
            ["bash", str(REPO_ROOT / "code" / "check_melodic_inputs.sh"), "--help"],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("mask coverage", qa.stdout)

    def test_melodic_input_qa_accepts_consistent_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fakebin = root / "bin"
            fakebin.mkdir()
            self.write_command(fakebin / "fslnvols", "echo 240\n")
            self.write_command(
                fakebin / "fslval",
                'case "$2" in dim1) echo 64;; dim2) echo 64;; dim3) echo 48;; *) echo 3.0;; esac\n',
            )
            self.write_command(
                fakebin / "fslorient",
                "printf '1 0 0 0\\n0 1 0 0\\n0 0 1 0\\n0 0 0 1\\n'\n",
            )
            self.write_command(
                fakebin / "fslmaths",
                'for argument in "$@"; do output="$argument"; done\nprintf x > "$output"\n',
            )
            self.write_command(
                fakebin / "fslstats",
                'case "$1" in '
                '*temporal_sd*) echo "98 980 1.25";; '
                '*outside_mask*) echo "0 0";; '
                '*brain_mask*) echo "100 1000";; '
                '*) echo "-2 2 0 1";; esac\n',
            )

            fmriprep = root / "derivatives" / "fmriprep-25.2.5" / "sub-001" / "func"
            denoised = root / "derivatives" / "fsl" / "denoised" / "sub-001" / "func"
            fmriprep.mkdir(parents=True)
            denoised.mkdir(parents=True)
            manifest = root / "derivatives" / "fsl" / "task-rest_run_manifest.tsv"
            input_list = root / "derivatives" / "fsl" / "melodic_filelist_5mm_denoised.txt"
            qc_tsv = root / "qc.tsv"
            manifest_rows = [
                "participant\tacquired_run\tcondition\tcondition_order\tevents\tbold\tconfounds"
            ]
            inputs = []
            for order, condition in enumerate(("sham", "rtpj", "vlpfc", "both"), start=1):
                run = f"{order:02d}"
                stem = f"sub-001_task-rest_run-{run}_space-MNI152NLin6Asym_res-native"
                bold = fmriprep / f"{stem}_desc-preproc_bold.nii.gz"
                mask = fmriprep / f"{stem}_desc-brain_mask.nii.gz"
                denoised_file = denoised / (
                    f"{stem}_condition-{condition}_order-{order:02d}"
                    "_desc-denoised_bold_5mm.nii.gz"
                )
                bold.write_text("x")
                mask.write_text("x")
                denoised_file.write_text("x")
                inputs.append(denoised_file)
                manifest_rows.append(
                    f"sub-001\t{run}\t{condition}\t{order}\tevents.tsv\t{bold}\tconfounds.tsv"
                )
            manifest.write_text("\n".join(manifest_rows) + "\n")
            input_list.write_text("".join(f"{path}\n" for path in inputs))

            result = subprocess.run(
                [
                    "bash",
                    str(REPO_ROOT / "code" / "check_melodic_inputs.sh"),
                    "--input-list",
                    str(input_list),
                    "--manifest",
                    str(manifest),
                    "--output-tsv",
                    str(qc_tsv),
                ],
                env=os.environ | {"PATH": f"{fakebin}:{os.environ['PATH']}"},
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("MELODIC inputs passed all checks", result.stderr)
            self.assertEqual(len(qc_tsv.read_text().splitlines()), 5)


if __name__ == "__main__":
    unittest.main()
