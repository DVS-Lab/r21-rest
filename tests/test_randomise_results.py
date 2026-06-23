from __future__ import annotations

import csv
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CHECKER = REPO_ROOT / "code" / "check_randomise_results.py"
CONTRASTS = (
    "both-minus-sham",
    "both-minus-rtpj",
    "both-minus-vlpfc",
    "rtpj-minus-vlpfc",
    "rtpj-minus-sham",
    "vlpfc-minus-sham",
    "both-minus-mean-rtpj-vlpfc",
)


class RandomiseResultTests(unittest.TestCase):
    @staticmethod
    def write_command(path: Path, body: str) -> None:
        path.write_text("#!/bin/sh\n" + body)
        path.chmod(0o755)

    def test_checks_both_directions_and_copies_significant_maps(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fsl_dir = root / "derivatives" / "fsl"
            diagnostics = fsl_dir / "diagnostics"
            diagnostics.mkdir(parents=True)
            comparison = diagnostics / "smith09_ica_comparison.tsv"
            comparison.write_text(
                "data_set\tdimension\tnetwork\tanalysis_priority\tbest_component\n"
                "denoised\tautomatic\tdefault_mode\tprimary\t23\n"
                "denoised\t20\tdefault_mode\tprimary\t10\n"
            )

            for analysis, label, component in (
                ("0", "denoised_dim-00_task-rest", 23),
                ("20", "denoised_dim-20_task-rest", 10),
            ):
                component_padded = f"{component:04d}"
                dr_dir = fsl_dir / f"dual-regression_{label}.dr"
                component_dir = (
                    dr_dir / "contrasts" / f"component-{component_padded}_stat-beta"
                )
                component_dir.mkdir(parents=True)
                (dr_dir / "mask.nii.gz").write_text("mask")
                (component_dir / "design.mat").write_text("design")
                (component_dir / "design.grp").write_text("group")
                (component_dir / "design.con").write_text(
                    "/ContrastName1\tPositive\n"
                    "/ContrastName2\tNegative\n"
                    "/NumWaves\t1\n"
                    "/NumContrasts\t2\n\n"
                    "/Matrix\n1\n-1\n"
                )
                (component_dir / "subject_order.tsv").write_text(
                    "randomise_index\tparticipant\n0\tsub-001\n1\tsub-002\n"
                )
                randomise_dir = component_dir / "randomise" / "network-dmn"
                randomise_dir.mkdir(parents=True)
                for contrast in CONTRASTS:
                    contrast_dir = component_dir / contrast
                    contrast_dir.mkdir()
                    group_input = contrast_dir / (
                        f"group_task-rest_component-{component_padded}_stat-beta_"
                        f"contrast-{contrast}.nii.gz"
                    )
                    group_input.write_text("group input")
                    prefix = randomise_dir / (
                        f"task-rest_network-dmn_component-{component_padded}_stat-beta_"
                        f"contrast-{contrast}"
                    )
                    Path(f"{prefix}.complete").write_text(
                        "n_perm\t5000\ncluster_threshold\t3.1\n"
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
                'case "$1" in *clustere_corrp_tstat1*) echo "0 0.97";; *) echo "0 0.94";; esac\n',
            )
            self.write_command(fakebin / "fslnvols", "echo 2\n")
            output_dir = fsl_dir / "randomise_summary"
            result = subprocess.run(
                [
                    "python3",
                    str(CHECKER),
                    "--network-set",
                    "dmn",
                    "--analysis-set",
                    "ica",
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

            self.assertIn("Design contrasts verified (+1/-1): 2/2", result.stdout)
            self.assertIn("Completion markers present: 14/14", result.stdout)
            self.assertIn("t-stat images present: 28/28", result.stdout)
            self.assertIn("corrp images present: 28/28", result.stdout)
            self.assertNotIn("TFCE maps", result.stdout)
            self.assertIn("Cluster-extent maps with peak > 0.95: 14", result.stdout)

            summary = output_dir / "task-rest_randomise_peak_summary.tsv"
            with summary.open(newline="") as stream:
                rows = list(csv.DictReader(stream, delimiter="\t"))
            self.assertEqual(len(rows), 28)
            self.assertEqual({row["design_contrast"] for row in rows}, {"C1", "C2"})
            self.assertEqual(
                {row["inference"] for row in rows}, {"cluster-extent"}
            )
            significant = [row for row in rows if row["peak_gt_threshold"] == "true"]
            self.assertEqual(len(significant), 14)
            self.assertTrue(all(row["copied_image"] for row in significant))

            copied_images = list(output_dir.glob("*.nii.gz"))
            copied_sidecars = list(output_dir.glob("*.json"))
            self.assertEqual(len(copied_images), 14)
            self.assertEqual(len(copied_sidecars), 14)
            sidecar = json.loads(copied_sidecars[0].read_text())
            self.assertEqual(sidecar["DesignContrast"], "C1")
            self.assertEqual(sidecar["InferenceMethod"], "cluster-extent")
            self.assertEqual(sidecar["ClusterFormingTThreshold"], 3.1)


if __name__ == "__main__":
    unittest.main()
