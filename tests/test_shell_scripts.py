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
            confound_file = root / "confounds.1D"
            confound_row = "\t".join(["0"] * 31)
            confound_file.write_text(f"{confound_row}\n{confound_row}\n")
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

            stale_confounds = root / "confounds.tsv"
            stale_confounds.write_text(confound_file.read_text())
            manifest.write_text(
                manifest.read_text().replace(str(confound_file), str(stale_confounds))
            )
            stale_batch = subprocess.run(
                [
                    "bash",
                    str(REPO_ROOT / "code" / "run_regress_confounds.sh"),
                    "--dry-run",
                ],
                env=env,
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(stale_batch.returncode, 0)
            self.assertIn("AFNI treats the first row", stale_batch.stderr)

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
                "denoised",
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

        all_smith = subprocess.run(
            [
                "bash",
                str(REPO_ROOT / "code" / "run_match_smith09.sh"),
                "--dry-run",
            ],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("melodic-concat_dim-00", all_smith.stderr)
        self.assertIn("melodic-concat_denoised_dim-20", all_smith.stderr)
        self.assertIn("summarize_smith09_analyses.py", all_smith.stderr)

        smith_dual = subprocess.run(
            [
                "bash",
                str(REPO_ROOT / "code" / "run_dual_regression_smith09.sh"),
                "denoised",
                "--dry-run",
            ],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("melodic_filelist_5mm_denoised.txt", smith_dual.stderr)
        self.assertIn("PNAS_Smith09_rsn10_resampled.nii.gz", smith_dual.stderr)
        self.assertIn("1 -1 0", smith_dual.stderr)

        for dimension, label in (("0", "dim-00"), ("20", "dim-20")):
            melodic_dual = subprocess.run(
                [
                    "bash",
                    str(REPO_ROOT / "code" / "run_dual_regression.sh"),
                    dimension,
                    "--dry-run",
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("melodic_filelist_5mm_denoised.txt", melodic_dual.stderr)
            self.assertIn(f"melodic-concat_denoised_{label}", melodic_dual.stderr)
            self.assertIn("1 -1 0", melodic_dual.stderr)

        contrasts = subprocess.run(
            [
                "bash",
                str(REPO_ROOT / "code" / "make_dual_regression_contrasts.sh"),
                "20",
                "10",
                "--dry-run",
            ],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("Component: 10 (FSL volume 9)", contrasts.stderr)
        self.assertIn("dr_stage2_subjectNNNNN.nii.gz", contrasts.stderr)
        self.assertIn("both-minus-mean-rtpj-vlpfc", contrasts.stderr)

        z_contrasts = subprocess.run(
            [
                "bash",
                str(REPO_ROOT / "code" / "make_dual_regression_contrasts.sh"),
                "smith09",
                "4",
                "--map-type",
                "z",
                "--dry-run",
            ],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("dr_stage2_subjectNNNNN_Z.nii.gz", z_contrasts.stderr)
        self.assertIn("Z maps are a sensitivity analysis", z_contrasts.stderr)

        qa = subprocess.run(
            ["bash", str(REPO_ROOT / "code" / "check_melodic_inputs.sh"), "--help"],
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertIn("mask coverage", qa.stdout)

    def test_dual_regression_contrasts_build_randomise_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fakebin = root / "bin"
            fakebin.mkdir()
            self.write_command(fakebin / "fslnvols", "echo 20\n")
            self.write_command(fakebin / "fslroi", 'printf x > "$2"\n')
            self.write_command(
                fakebin / "fslmaths",
                'for argument in "$@"; do third="$second"; second="$last"; last="$argument"; done\n'
                'printf x > "$third"\n',
            )
            self.write_command(fakebin / "fslmerge", 'printf x > "$2"\n')

            drdir = root / "dual-regression_denoised_dim-20_task-rest.dr"
            drdir.mkdir()
            (drdir / "mask.nii.gz").write_text("x")
            labels = ("subject00000", "subject00001", "subject00002", "subject00003")
            conditions = ("vlpfc", "sham", "both", "rtpj")
            runs = ("03", "01", "04", "02")
            mapping = [
                "dual_regression_index\tdual_regression_label\tparticipant\trun\tcondition\tcondition_order\tfile"
            ]
            for index, (label, condition, run) in enumerate(zip(labels, conditions, runs)):
                stage2 = drdir / f"dr_stage2_{label}.nii.gz"
                stage2.write_text("x")
                mapping.append(
                    f"{index}\t{label}\tsub-001\t{run}\t{condition}\t{index + 1}\tinput{index}.nii.gz"
                )
            (drdir / "input_order.tsv").write_text("\n".join(mapping) + "\n")

            result = subprocess.run(
                [
                    "bash",
                    str(REPO_ROOT / "code" / "make_dual_regression_contrasts.sh"),
                    "20",
                    "10",
                ],
                env=os.environ
                | {
                    "PATH": f"{fakebin}:{os.environ['PATH']}",
                    "DUAL_REGRESSION_DIR": str(drdir),
                    "WORK_ROOT": str(root / "scratch"),
                },
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)

            output = drdir / "contrasts" / "component-0010_stat-beta"
            self.assertIn("Participants: 1", result.stderr)
            self.assertEqual(
                (output / "subject_order.tsv").read_text(),
                "randomise_index\tparticipant\n0\tsub-001\n",
            )
            self.assertEqual((output / "design.mat").read_text().count("\n1\n"), 1)
            self.assertIn("/ContrastName2\tNegative", (output / "design.con").read_text())
            randomise = (output / "run_randomise.sh").read_text()
            self.assertEqual(randomise.count("randomise -i"), 7)
            self.assertIn('-n "$nperm" -T', randomise)
            for contrast in (
                "both-minus-sham",
                "both-minus-rtpj",
                "both-minus-vlpfc",
                "rtpj-minus-vlpfc",
                "rtpj-minus-sham",
                "vlpfc-minus-sham",
                "both-minus-mean-rtpj-vlpfc",
            ):
                group_input = output / contrast / (
                    "group_task-rest_component-0010_stat-beta_"
                    f"contrast-{contrast}.nii.gz"
                )
                self.assertTrue(group_input.exists())

    def test_melodic_input_qa_accepts_consistent_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fakebin = root / "bin"
            fakebin.mkdir()
            self.write_command(fakebin / "3dinfo", "printf '1\\n1\\n'\n")
            self.write_command(fakebin / "fslnvols", "echo 240\n")
            self.write_command(
                fakebin / "fslval",
                'case "$2" in dim1) echo 64;; dim2) echo 64;; dim3) echo 48;; *) echo 3.0;; esac\n',
            )
            self.write_command(
                fakebin / "fslmaths",
                'for argument in "$@"; do output="$argument"; done\nprintf x > "$output"\n',
            )
            self.write_command(
                fakebin / "fslstats",
                'case "$1" in '
                '*pre_temporal_sd*) echo "100 1000 2.0";; '
                '*post_temporal_sd*) echo "98 980 1.25";; '
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
            confounds = root / "confounds.1D"
            confounds.write_text("\t".join(["0"] * 31) + "\n")
            inputs = []
            for order, condition in enumerate(("sham", "rtpj", "vlpfc", "both"), start=1):
                run = f"{order:02d}"
                stem = f"sub-001_task-rest_run-{run}_space-MNI152NLin6Asym_res-native"
                bold = fmriprep / f"{stem}_desc-preproc_bold.nii.gz"
                mask = fmriprep / f"{stem}_desc-brain_mask.nii.gz"
                smoothed = fmriprep / (
                    f"{stem}_condition-{condition}_order-{order:02d}"
                    "_desc-preproc_bold_5mm.nii.gz"
                )
                denoised_file = denoised / (
                    f"{stem}_condition-{condition}_order-{order:02d}"
                    "_desc-denoised_bold_5mm.nii.gz"
                )
                bold.write_text("x")
                mask.write_text("x")
                smoothed.write_text("x")
                denoised_file.write_text("x")
                inputs.append(denoised_file)
                manifest_rows.append(
                    f"sub-001\t{run}\t{condition}\t{order}\tevents.tsv\t{bold}\t{confounds}"
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
            lines = qc_tsv.read_text().splitlines()
            self.assertEqual(len(lines), 5)
            header = lines[0].split("\t")
            first_run = dict(zip(header, lines[1].split("\t")))
            self.assertEqual(first_run["confound_columns"], "31")
            self.assertEqual(first_run["temporal_sd_ratio"], "0.625000")
            self.assertEqual(first_run["status"], "ok")

            self.write_command(
                fakebin / "fslstats",
                'case "$1" in '
                '*pre_temporal_sd*) echo "100 1000 2.0";; '
                '*post_temporal_sd*) echo "98 980 2.0";; '
                '*outside_mask*) echo "0 0";; '
                '*brain_mask*) echo "100 1000";; '
                '*) echo "-2 2 0 1";; esac\n',
            )
            self.write_command(fakebin / "3dinfo", "printf '0\\n0\\n'\n")
            failed_result = subprocess.run(
                [
                    "bash",
                    str(REPO_ROOT / "code" / "check_melodic_inputs.sh"),
                    "--input-list",
                    str(input_list),
                    "--manifest",
                    str(manifest),
                    "--output-tsv",
                    str(root / "failed_qc.tsv"),
                ],
                env=os.environ | {"PATH": f"{fakebin}:{os.environ['PATH']}"},
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(failed_result.returncode, 0)
            self.assertIn("Failure counts:", failed_result.stderr)
            self.assertIn("mask_grid_mismatch: 4", failed_result.stderr)
            self.assertIn("no_variance_removed: 4", failed_result.stderr)


if __name__ == "__main__":
    unittest.main()
