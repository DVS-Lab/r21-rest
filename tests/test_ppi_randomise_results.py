from __future__ import annotations

import csv
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / "code" / "check_ppi_randomise_results.py"
CONTRASTS = (
    "both-minus-sham",
    "both-minus-rtpj",
    "both-minus-vlpfc",
    "rtpj-minus-vlpfc",
    "rtpj-minus-sham",
    "vlpfc-minus-sham",
    "both-minus-mean-rtpj-vlpfc",
)


class PPIRandomiseResultTests(unittest.TestCase):
    @staticmethod
    def write_command(path: Path, body: str) -> None:
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)

    def test_compiles_ppi_randomise_outputs_and_copies_significant_maps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ppi_dir = root / "derivatives" / "fsl" / "dual-regression_smith09_denoised_ppi-dmn-ecn.dr"
            component = ppi_dir / "contrasts" / "component-0011_stat-beta"
            randomise_dir = component / "randomise"
            randomise_dir.mkdir(parents=True)
            (ppi_dir / "mask.nii.gz").write_text("mask")
            (component / "design.mat").write_text("design")
            (component / "design.grp").write_text("group")
            (component / "design.con").write_text(
                "/ContrastName1\tPositive\n"
                "/ContrastName2\tNegative\n"
                "/NumWaves\t1\n"
                "/NumContrasts\t2\n\n"
                "/Matrix\n1\n-1\n"
            )
            (component / "subject_order.tsv").write_text(
                "randomise_index\tparticipant\n0\tsub-001\n1\tsub-002\n"
            )
            input_order = [
                "dual_regression_index\tdual_regression_label\tparticipant\trun\tcondition"
            ]
            index = 0
            for participant in ("sub-001", "sub-002"):
                for run, condition in enumerate(("sham", "rtpj", "vlpfc", "both"), start=1):
                    label = f"subject{index:05d}"
                    input_order.append(
                        f"{index}\t{label}\t{participant}\t{run:02d}\t{condition}"
                    )
                    (ppi_dir / f"dr_stage2_{label}.nii.gz").write_text("stage2")
                    index += 1
            (ppi_dir / "input_order.tsv").write_text("\n".join(input_order) + "\n")
            for contrast in CONTRASTS:
                contrast_dir = component / contrast
                contrast_dir.mkdir()
                group_input = contrast_dir / (
                    "group_task-rest_component-0011_stat-beta_"
                    f"contrast-{contrast}.nii.gz"
                )
                group_input.write_text("group input")
                prefix = randomise_dir / (
                    "task-rest_component-0011_stat-beta_"
                    f"contrast-{contrast}"
                )
                for number in (1, 2):
                    Path(f"{prefix}_tstat{number}.nii.gz").write_text("tstat")
                    Path(f"{prefix}_clustere_corrp_tstat{number}.nii.gz").write_text(
                        "cluster"
                    )

            fakebin = root / "bin"
            fakebin.mkdir()
            self.write_command(
                fakebin / "fslstats",
                'case "$*" in *" -m") echo "0.25";; '
                '*clustere_corrp_tstat1*) echo "0 0.98";; *) echo "0 0.94";; esac\n',
            )
            self.write_command(fakebin / "fslnvols", "echo 2\n")
            self.write_command(
                fakebin / "fslmaths",
                'for argument in "$@"; do output="$argument"; done\nprintf x > "$output"\n',
            )
            self.write_command(fakebin / "fslroi", 'printf x > "$2"\n')
            output_dir = root / "derivatives" / "fsl" / "ppi_randomise_summary"

            result = subprocess.run(
                [
                    sys.executable,
                    str(CHECKER),
                    "--ppi-dir",
                    str(ppi_dir),
                    "--output-dir",
                    str(output_dir),
                    "--fail-on-missing",
                ],
                env=os.environ | {"PATH": f"{fakebin}:{os.environ['PATH']}"},
                text=True,
                capture_output=True,
                check=True,
            )

            self.assertIn("t-stat images present: 14/14", result.stdout)
            self.assertIn("corrp images present: 14/14", result.stdout)
            self.assertIn("Corrected maps with peak > 0.95: 7", result.stdout)
            self.assertIn("ROI-value TSVs written: 7 (56 rows)", result.stdout)

            summary = output_dir / "task-rest_ppi-dmn-ecn_randomise_peak_summary.tsv"
            with summary.open(newline="") as stream:
                rows = list(csv.DictReader(stream, delimiter="\t"))
            self.assertEqual(len(rows), 14)
            self.assertEqual({row["network"] for row in rows}, {"dmn-x-ecn"})
            self.assertEqual({row["component"] for row in rows}, {"11"})
            self.assertEqual(
                len([row for row in rows if row["peak_gt_threshold"] == "true"]),
                7,
            )
            copied_images = list(output_dir.glob("*.nii.gz"))
            copied_sidecars = list(output_dir.glob("*.json"))
            roi_values = list(output_dir.glob("*_timeseries.tsv"))
            self.assertEqual(len(copied_images), 7)
            self.assertEqual(len(copied_sidecars), 7)
            self.assertEqual(len(roi_values), 7)


if __name__ == "__main__":
    unittest.main()
