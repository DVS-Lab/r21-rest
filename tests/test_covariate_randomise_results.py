from __future__ import annotations

import csv
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / "code" / "check_covariate_randomise_results.py"


class CovariateRandomiseResultTests(unittest.TestCase):
    @staticmethod
    def write_command(path: Path, body: str) -> None:
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)

    def test_compiles_four_contrasts_and_extracts_significant_roi_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fsl_dir = root / "derivatives" / "fsl"
            model_dir = (
                fsl_dir
                / "dual-regression_smith09_denoised.dr"
                / "contrasts"
                / "component-0004_stat-beta"
                / "covariate-models"
                / "model-cov-fdmean-blink"
            )
            contrast_dir = model_dir / "rtpj-minus-vlpfc"
            randomise_dir = model_dir / "randomise" / "network-dmn"
            contrast_dir.mkdir(parents=True)
            randomise_dir.mkdir(parents=True)

            group_input = contrast_dir / "group_task-rest_component-0004_stat-beta_contrast-rtpj-minus-vlpfc_model-cov-fdmean-blink.nii.gz"
            design_mat = contrast_dir / "design.mat"
            design_con = contrast_dir / "design.con"
            design_grp = contrast_dir / "design.grp"
            audit = contrast_dir / "covariate_audit.tsv"
            group_input.write_text("group")
            design_mat.write_text("/NumWaves\t3\n/NumPoints\t2\n\n/Matrix\n1\t-0.1\t-2\n1\t0.1\t2\n")
            design_con.write_text(
                "/ContrastName1\tmean_pos\n"
                "/ContrastName2\tmean_neg\n"
                "/ContrastName3\tcov_pos\n"
                "/ContrastName4\tcov_neg\n"
                "/NumWaves\t3\n"
                "/NumContrasts\t4\n\n"
                "/Matrix\n"
                "1\t0\t0\n"
                "-1\t0\t0\n"
                "0\t0\t1\n"
                "0\t0\t-1\n"
            )
            design_grp.write_text("/NumWaves\t1\n/NumPoints\t2\n\n/Matrix\n1\n1\n")
            audit.write_text(
                "randomise_index\tparticipant\tdelta_fd_mean\tdelta_fd_mean_demeaned\tdelta_blink_rate_per_min\tdelta_blink_rate_per_min_demeaned\n"
                "0\tsub-001\t0.1\t-0.1\t1.0\t-2.0\n"
                "1\tsub-002\t0.3\t0.1\t5.0\t2.0\n"
            )
            output_prefix = randomise_dir / (
                "task-rest_network-dmn_component-0004_stat-beta_"
                "contrast-rtpj-minus-vlpfc_model-cov-fdmean-blink"
            )
            Path(f"{output_prefix}.complete").write_text("done\n")
            for number in (1, 2, 3, 4):
                Path(f"{output_prefix}_tstat{number}.nii.gz").write_text("tstat")
                Path(f"{output_prefix}_clustere_corrp_tstat{number}.nii.gz").write_text("corrp")

            (model_dir / "randomise_jobs.tsv").write_text(
                "contrast\tnetwork\tgroup_input\tdesign_mat\tdesign_con\tdesign_grp\toutput_prefix\n"
                f"rtpj-minus-vlpfc\tdmn\t{group_input}\t{design_mat}\t{design_con}\t{design_grp}\t{output_prefix}\n"
            )

            fakebin = root / "bin"
            fakebin.mkdir()
            self.write_command(
                fakebin / "fslstats",
                'case "$*" in *" -m") echo "0.25";; '
                '*clustere_corrp_tstat3*) echo "0 0.97";; *) echo "0 0.94";; esac\n',
            )
            self.write_command(fakebin / "fslnvols", "echo 2\n")
            self.write_command(
                fakebin / "fslmaths",
                'for argument in "$@"; do output="$argument"; done\nprintf x > "$output"\n',
            )
            self.write_command(fakebin / "fslroi", 'printf x > "$2"\n')

            output_dir = fsl_dir / "covariate_randomise_summary"
            result = subprocess.run(
                [
                    "python3",
                    str(CHECKER),
                    "--fsl-dir",
                    str(fsl_dir),
                    "--output-dir",
                    str(output_dir),
                    "--fail-on-missing",
                ],
                env=os.environ | {"PATH": f"{fakebin}:{os.environ['PATH']}"},
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertIn("Randomise jobs checked: 1", result.stdout)
            self.assertIn("Summary rows: 4/4", result.stdout)
            self.assertIn("Significant maps with peak > 0.95: 1", result.stdout)
            self.assertIn("ROI-value TSVs written: 1 (2 rows)", result.stdout)

            summary = output_dir / "task-rest_covariate-randomise_peak_summary.tsv"
            with summary.open(newline="") as stream:
                rows = list(csv.DictReader(stream, delimiter="\t"))
            self.assertEqual(len(rows), 4)
            self.assertEqual({row["design_contrast"] for row in rows}, {"C1", "C2", "C3", "C4"})
            significant = [row for row in rows if row["peak_gt_threshold"] == "true"]
            self.assertEqual(len(significant), 1)
            self.assertEqual(significant[0]["design_contrast"], "C3")
            self.assertEqual(significant[0]["tested_covariate"], "delta_blink_rate_per_min")
            self.assertTrue(significant[0]["copied_image"].endswith(".nii.gz"))
            self.assertTrue(significant[0]["roi_values_tsv"].endswith("_values.tsv"))

            roi_path = REPO_ROOT / significant[0]["roi_values_tsv"]
            with roi_path.open(newline="") as stream:
                roi_rows = list(csv.DictReader(stream, delimiter="\t"))
            self.assertEqual(len(roi_rows), 2)
            self.assertEqual({row["subject_contrast_beta"] for row in roi_rows}, {"0.25"})
            self.assertEqual(roi_rows[0]["delta_blink_rate_per_min_demeaned"], "-2.0")

            sidecar = json.loads((REPO_ROOT / significant[0]["copied_sidecar"]).read_text())
            self.assertEqual(sidecar["DesignContrast"], "C3")
            self.assertEqual(sidecar["TestedCovariate"], "delta_blink_rate_per_min")


if __name__ == "__main__":
    unittest.main()
