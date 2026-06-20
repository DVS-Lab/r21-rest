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


class SummarizeFslccTests(unittest.TestCase):
    def test_writes_labeled_best_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "fslcc_output.txt"
            lines = []
            for component in range(1, 4):
                for network in range(1, 11):
                    value = component / 10 + network / 1000
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
            self.assertEqual(rows[3]["best_component"], "3")
            self.assertEqual(rows[4]["network"], "cerebellum")
            self.assertEqual(rows[4]["analysis_priority"], "secondary")

    def test_rejects_incomplete_matrix(self):
        correlations = {(1, network): 0.1 for network in range(1, 10)}
        with self.assertRaises(ValueError):
            summary.validate_matrix(correlations)


if __name__ == "__main__":
    unittest.main()
