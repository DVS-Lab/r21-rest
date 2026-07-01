#!/usr/bin/env python3
"""Summarize dual-regression stage-1 network correlations by condition."""

from __future__ import annotations

import argparse
import csv
import math
import sys
from itertools import combinations
from pathlib import Path

import numpy as np


CONDITIONS = ("sham", "rtpj", "vlpfc", "both")
CONTRAST_WEIGHTS = {
    "both-minus-sham": {"both": 1.0, "sham": -1.0},
    "both-minus-rtpj": {"both": 1.0, "rtpj": -1.0},
    "both-minus-vlpfc": {"both": 1.0, "vlpfc": -1.0},
    "rtpj-minus-vlpfc": {"rtpj": 1.0, "vlpfc": -1.0},
    "rtpj-minus-sham": {"rtpj": 1.0, "sham": -1.0},
    "vlpfc-minus-sham": {"vlpfc": 1.0, "sham": -1.0},
    "both-minus-mean-rtpj-vlpfc": {"both": 1.0, "rtpj": -0.5, "vlpfc": -0.5},
}
SMITH09_LABELS = (
    ("primary-visual", 1),
    ("occipital-pole", 2),
    ("lateral-visual", 3),
    ("dmn", 4),
    ("cerebellum", 5),
    ("sensorimotor", 6),
    ("auditory", 7),
    ("ecn", 8),
    ("right-fpn", 9),
    ("left-fpn", 10),
)
PRIMARY_NETWORKS = {"dmn", "ecn", "right-fpn", "left-fpn"}
NONCEREBELLAR_NETWORKS = {name for name, _component in SMITH09_LABELS if name != "cerebellum"}


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--analysis",
        default="smith09_denoised",
        help="Dual-regression analysis label after dual-regression_ (default: smith09_denoised).",
    )
    parser.add_argument(
        "--network-set",
        choices=("dmn-ecn", "primary", "all-noncerebellar", "all"),
        default="all-noncerebellar",
        help="Network pairs to summarize. dmn-ecn reports only the DMN/ECN pair.",
    )
    parser.add_argument(
        "--dr-dir",
        type=Path,
        help="Completed dual-regression directory. Defaults to derivatives/fsl/dual-regression_ANALYSIS.dr.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_root / "derivatives" / "fsl" / "network_correlation_summary",
        help="Directory for tracked TSV outputs.",
    )
    parser.add_argument("--n-perm", type=int, default=100000)
    parser.add_argument("--seed", type=int, default=20260701)
    parser.add_argument("--fail-on-missing", action="store_true")
    return parser.parse_args()


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def selected_networks(network_set: str) -> list[tuple[str, int]]:
    if network_set == "dmn-ecn":
        keep = {"dmn", "ecn"}
    elif network_set == "primary":
        keep = PRIMARY_NETWORKS
    elif network_set == "all-noncerebellar":
        keep = NONCEREBELLAR_NETWORKS
    else:
        keep = {name for name, _component in SMITH09_LABELS}
    return [(name, component) for name, component in SMITH09_LABELS if name in keep]


def read_stage1(path: Path, expected_columns: int) -> np.ndarray:
    matrix = np.loadtxt(path, dtype=float)
    if matrix.ndim != 2:
        raise ValueError(f"Stage-1 matrix is not 2D: {path}")
    if matrix.shape[1] == expected_columns:
        return matrix
    if matrix.shape[0] == expected_columns:
        return matrix.T
    raise ValueError(
        f"Stage-1 matrix has shape {matrix.shape}, expected one dimension to be {expected_columns}: {path}"
    )


def correlation_matrices(matrix: np.ndarray) -> dict[str, np.ndarray]:
    full = np.corrcoef(matrix, rowvar=False)
    precision = np.linalg.pinv(full)
    denom = np.sqrt(np.outer(np.diag(precision), np.diag(precision)))
    partial = -precision / denom
    np.fill_diagonal(partial, 1.0)
    return {"full": full, "partial": partial}


def fisher_z(value: float) -> float:
    clipped = min(max(value, -0.999999), 0.999999)
    return math.atanh(clipped)


def format_float(value: float) -> str:
    if value is None or not math.isfinite(value):
        return "n/a"
    return f"{value:.10g}"


def condition_lookup(rows: list[dict[str, object]]) -> dict[tuple[str, str, str, str], dict[str, object]]:
    return {
        (
            str(row["participant"]),
            str(row["correlation_type"]),
            str(row["network_pair"]),
            str(row["condition"]),
        ): row
        for row in rows
    }


def permutation_p(values: np.ndarray, n_perm: int, seed: int) -> tuple[float, float]:
    observed = float(np.mean(values))
    if values.size == 0:
        return math.nan, math.nan
    rng = np.random.default_rng(seed)
    signs = rng.choice((-1.0, 1.0), size=(n_perm, values.size))
    permuted = signs @ values / values.size
    p_two = (np.count_nonzero(np.abs(permuted) >= abs(observed)) + 1.0) / (n_perm + 1.0)
    return observed, float(p_two)


def main() -> int:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]
    dr_dir = args.dr_dir or project_root / "derivatives" / "fsl" / f"dual-regression_{args.analysis}.dr"
    input_order = dr_dir / "input_order.tsv"
    if not input_order.is_file():
        message = f"ERROR: input_order.tsv not found: {input_order}"
        if args.fail_on_missing:
            print(message, file=sys.stderr)
            return 1
        print(message, file=sys.stderr)
        return 0

    networks = selected_networks(args.network_set)
    component_to_network = {component: name for name, component in networks}
    pairs = list(combinations(networks, 2))
    if args.network_set == "dmn-ecn":
        pairs = [(("dmn", 4), ("ecn", 8))]

    raw_rows: list[dict[str, object]] = []
    missing: list[str] = []
    for item in read_tsv(input_order):
        label = item["dual_regression_label"]
        stage1 = dr_dir / f"dr_stage1_{label}.txt"
        if not stage1.is_file():
            missing.append(str(stage1))
            continue
        matrix = read_stage1(stage1, len(SMITH09_LABELS))
        matrices = correlation_matrices(matrix)
        for corr_type, corr in matrices.items():
            for (network_a, component_a), (network_b, component_b) in pairs:
                r_value = float(corr[component_a - 1, component_b - 1])
                raw_rows.append(
                    {
                        "analysis": args.analysis,
                        "correlation_type": corr_type,
                        "network_a": network_a,
                        "component_a": component_a,
                        "network_b": network_b,
                        "component_b": component_b,
                        "network_pair": f"{network_a}__{network_b}",
                        "participant": item["participant"],
                        "run": item["run"],
                        "condition": item["condition"],
                        "condition_order": item.get("condition_order", ""),
                        "dual_regression_label": label,
                        "n_timepoints": matrix.shape[0],
                        "r": format_float(r_value),
                        "fisher_z": format_float(fisher_z(r_value)),
                    }
                )

    if missing:
        print(f"Missing stage-1 files: {len(missing)}", file=sys.stderr)
        for path in missing[:10]:
            print(f"  {path}", file=sys.stderr)
        if args.fail_on_missing:
            return 1

    raw_fields = [
        "analysis",
        "correlation_type",
        "network_a",
        "component_a",
        "network_b",
        "component_b",
        "network_pair",
        "participant",
        "run",
        "condition",
        "condition_order",
        "dual_regression_label",
        "n_timepoints",
        "r",
        "fisher_z",
    ]
    stem = f"task-rest_analysis-{args.analysis}_network-correlation"
    raw_path = args.output_dir / f"{stem}_run-values.tsv"
    write_tsv(raw_path, raw_rows, raw_fields)

    lookup = condition_lookup(raw_rows)
    subjects = sorted({str(row["participant"]) for row in raw_rows})
    corr_types = sorted({str(row["correlation_type"]) for row in raw_rows})
    pair_labels = sorted({str(row["network_pair"]) for row in raw_rows})
    contrast_rows: list[dict[str, object]] = []
    for participant in subjects:
        for corr_type in corr_types:
            for pair in pair_labels:
                for contrast, weights in CONTRAST_WEIGHTS.items():
                    values: dict[str, float] = {}
                    complete = True
                    for condition in CONDITIONS:
                        key = (participant, corr_type, pair, condition)
                        row = lookup.get(key)
                        if row is None:
                            complete = False
                            continue
                        values[condition] = float(row["fisher_z"])
                    delta = math.nan
                    if complete:
                        delta = sum(weights.get(condition, 0.0) * values[condition] for condition in CONDITIONS)
                    contrast_rows.append(
                        {
                            "analysis": args.analysis,
                            "correlation_type": corr_type,
                            "network_pair": pair,
                            "condition_contrast": contrast,
                            "participant": participant,
                            "complete": str(complete).lower(),
                            "sham_z": format_float(values.get("sham", math.nan)),
                            "rtpj_z": format_float(values.get("rtpj", math.nan)),
                            "vlpfc_z": format_float(values.get("vlpfc", math.nan)),
                            "both_z": format_float(values.get("both", math.nan)),
                            "delta_fisher_z": format_float(delta),
                        }
                    )
    contrast_fields = [
        "analysis",
        "correlation_type",
        "network_pair",
        "condition_contrast",
        "participant",
        "complete",
        "sham_z",
        "rtpj_z",
        "vlpfc_z",
        "both_z",
        "delta_fisher_z",
    ]
    contrast_path = args.output_dir / f"{stem}_condition-contrasts.tsv"
    write_tsv(contrast_path, contrast_rows, contrast_fields)

    summary_rows: list[dict[str, object]] = []
    for corr_type in corr_types:
        for pair in pair_labels:
            for contrast in CONTRAST_WEIGHTS:
                values = np.array(
                    [
                        float(row["delta_fisher_z"])
                        for row in contrast_rows
                        if row["complete"] == "true"
                        and row["correlation_type"] == corr_type
                        and row["network_pair"] == pair
                        and row["condition_contrast"] == contrast
                    ],
                    dtype=float,
                )
                if values.size:
                    mean_delta, p_perm = permutation_p(
                        values,
                        args.n_perm,
                        args.seed + len(summary_rows),
                    )
                    sd = float(np.std(values, ddof=1)) if values.size > 1 else math.nan
                    sem = sd / math.sqrt(values.size) if values.size > 1 else math.nan
                    t_value = mean_delta / sem if sem and math.isfinite(sem) and sem > 0 else math.nan
                else:
                    mean_delta = p_perm = sd = sem = t_value = math.nan
                summary_rows.append(
                    {
                        "analysis": args.analysis,
                        "correlation_type": corr_type,
                        "network_pair": pair,
                        "condition_contrast": contrast,
                        "n": values.size,
                        "mean_delta_fisher_z": format_float(mean_delta),
                        "sd_delta_fisher_z": format_float(sd),
                        "sem_delta_fisher_z": format_float(sem),
                        "t_1sample": format_float(t_value),
                        "p_signflip_two_sided": format_float(p_perm),
                        "n_permutations": args.n_perm,
                    }
                )
    summary_fields = [
        "analysis",
        "correlation_type",
        "network_pair",
        "condition_contrast",
        "n",
        "mean_delta_fisher_z",
        "sd_delta_fisher_z",
        "sem_delta_fisher_z",
        "t_1sample",
        "p_signflip_two_sided",
        "n_permutations",
    ]
    summary_path = args.output_dir / f"{stem}_summary.tsv"
    write_tsv(summary_path, summary_rows, summary_fields)

    readme = args.output_dir / "README.md"
    if not readme.exists():
        readme.write_text(
            "# Network Correlation Summary\n\n"
            "Generated by `code/MakeNetworkCorrelationTables.py` from dual-regression "
            "stage-1 timecourse files. The run-values table contains Pearson full "
            "correlations and precision-matrix partial correlations among Smith09 "
            "network timecourses. The condition-contrast table applies the same "
            "within-participant condition contrasts used for the randomise analyses "
            "to Fisher-z-transformed correlations. The summary table reports one-sample "
            "means and deterministic Monte Carlo sign-flip p-values for each contrast.\n"
        )

    print(f"Network pairs: {len(pairs)}")
    print(f"Run correlation rows: {len(raw_rows)}")
    print(f"Wrote {raw_path}")
    print(f"Wrote {contrast_path}")
    print(f"Wrote {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
