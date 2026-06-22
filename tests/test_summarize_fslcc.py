from __future__ import annotations

import csv
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "code" / "gen_fslcc_table.py"
SPEC = importlib.util.spec_from_file_location("gen_fslcc_table", MODULE_PATH)
summary = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = summary
SPEC.loader.exec_module(summary)

COMPARISON_PATH = (
    Path(__file__).resolve().parents[1] / "code" / "summarize_smith09_analyses.py"
)
COMPARISON_SPEC = importlib.util.spec_from_file_location(
    "summarize_smith09_analyses", COMPARISON_PATH
)
comparison = importlib.util.module_from_spec(COMPARISON_SPEC)
assert COMPARISON_SPEC.loader is not None
sys.modules[COMPARISON_SPEC.name] = comparison
COMPARISON_SPEC.loader.exec_module(comparison)


class SummarizeFslccTests(unittest.TestCase):
    def test_writes_labeled_best_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "fslcc_output.txt"
            lines = []
            for component in range(1, 4):
                for network in range(1, 11):
                    value = component / 10 + network / 1000
                    if component == 1 and network == 4:
                        value = -0.9
                    lines.append(f"{component} {network} {value}\n")
            source.write_text("".join(lines))

            correlations = summary.read_fslcc(source)
            components = summary.validate_matrix(correlations)
            output = root / "best.tsv"
            summary.write_best_matches(output, correlations, components)

            with output.open() as stream:
                rows = list(csv.DictReader(stream, delimiter="\t"))
            self.assertEqual(len(rows), 10)
            self.assertEqual(rows[3]["network"], "default_mode")
            self.assertEqual(rows[3]["analysis_priority"], "primary")
            self.assertEqual(rows[3]["best_component"], "1")
            self.assertEqual(rows[3]["correlation"], "-0.9")
            self.assertEqual(rows[3]["absolute_correlation"], "0.9")
            self.assertEqual(rows[3]["sign"], "negative")
            self.assertEqual(rows[4]["network"], "cerebellum")
            self.assertEqual(rows[4]["analysis_priority"], "secondary")

    def test_rejects_incomplete_matrix(self):
        correlations = {(1, network): 0.1 for network in range(1, 10)}
        with self.assertRaises(ValueError):
            summary.validate_matrix(correlations)

    def test_combines_four_analysis_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            fsl_dir = Path(tmp)
            fieldnames = [
                "smith09_map",
                "network",
                "analysis_priority",
                "best_component",
                "correlation",
                "absolute_correlation",
                "sign",
                "next_component",
                "next_correlation",
                "next_absolute_correlation",
            ]
            for data_set, dimension, directory in comparison.ANALYSES:
                analysis_dir = fsl_dir / directory
                analysis_dir.mkdir()
                with (analysis_dir / "smith09_best_matches.tsv").open(
                    "w", newline=""
                ) as stream:
                    writer = csv.DictWriter(
                        stream,
                        fieldnames=fieldnames,
                        delimiter="\t",
                        lineterminator="\n",
                    )
                    writer.writeheader()
                    for network in range(1, 11):
                        writer.writerow(
                            {
                                "smith09_map": network,
                                "network": f"network_{network}",
                                "analysis_priority": "primary",
                                "best_component": 2,
                                "correlation": -0.7,
                                "absolute_correlation": 0.7,
                                "sign": "negative",
                                "next_component": 1,
                                "next_correlation": 0.4,
                                "next_absolute_correlation": 0.4,
                            }
                        )
                (analysis_dir / "smith09_component_correlations.tsv").write_text(
                    "melodic_component\tnetwork_1\n1\t0.1\n2\t0.2\n"
                )

                rows = comparison.read_analysis(
                    fsl_dir, data_set, dimension, directory
                )
                self.assertEqual(len(rows), 10)
                self.assertEqual(rows[0]["n_components"], "2")
                self.assertEqual(rows[0]["absolute_correlation_margin"], "0.3")

            output = fsl_dir / "comparison.tsv"
            original_argv = sys.argv
            try:
                sys.argv = [
                    str(COMPARISON_PATH),
                    "--fsl-dir",
                    str(fsl_dir),
                    "--output",
                    str(output),
                ]
                self.assertEqual(comparison.main(), 0)
            finally:
                sys.argv = original_argv
            with output.open() as stream:
                combined = list(csv.DictReader(stream, delimiter="\t"))
            self.assertEqual(len(combined), 40)


if __name__ == "__main__":
    unittest.main()
