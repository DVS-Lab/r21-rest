#!/usr/bin/env python3
"""Turn Smith09 fslcc output into labeled component-matching tables."""

from __future__ import annotations

import argparse
import csv
import statistics
from pathlib import Path


NETWORKS = [
    (1, "primary_visual", "other"),
    (2, "occipital_pole", "other"),
    (3, "lateral_visual", "other"),
    (4, "default_mode", "primary"),
    (5, "cerebellum", "secondary"),
    (6, "sensorimotor", "secondary"),
    (7, "auditory", "other"),
    (8, "executive_control", "primary"),
    (9, "right_frontoparietal", "primary"),
    (10, "left_frontoparietal", "primary"),
]


def read_fslcc(path: Path) -> dict[tuple[int, int], float]:
    correlations: dict[tuple[int, int], float] = {}
    for line_number, raw_line in enumerate(path.read_text().splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        fields = line.split()
        if len(fields) != 3:
            raise ValueError(f"{path}:{line_number}: expected three columns")
        try:
            component, network = int(fields[0]), int(fields[1])
            correlation = float(fields[2])
        except ValueError as error:
            raise ValueError(f"{path}:{line_number}: invalid fslcc values") from error
        key = (component, network)
        if key in correlations:
            raise ValueError(f"{path}:{line_number}: duplicate pair {key}")
        correlations[key] = correlation
    if not correlations:
        raise ValueError(f"No correlations found in: {path}")
    return correlations


def validate_matrix(correlations: dict[tuple[int, int], float]) -> list[int]:
    components = sorted({component for component, _ in correlations})
    networks = sorted({network for _, network in correlations})
    if networks != list(range(1, 11)):
        raise ValueError(f"Expected Smith09 maps 1-10; found: {networks}")
    missing = [
        (component, network)
        for component in components
        for network in networks
        if (component, network) not in correlations
    ]
    if missing:
        raise ValueError(f"Missing {len(missing)} component/network correlations")
    return components


def write_matrix(
    path: Path,
    correlations: dict[tuple[int, int], float],
    components: list[int],
) -> None:
    labels = [label for _, label, _ in NETWORKS]
    with path.open("w", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
        writer.writerow(["melodic_component", *labels])
        for component in components:
            writer.writerow(
                [
                    component,
                    *(
                        f"{correlations[(component, network)]:.8g}"
                        for network in range(1, 11)
                    ),
                ]
            )


def write_best_matches(
    path: Path,
    correlations: dict[tuple[int, int], float],
    components: list[int],
) -> None:
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
        "other_mean",
        "other_sd",
        "other_min",
        "other_max",
    ]
    rows = []
    for network, label, priority in NETWORKS:
        ordered = sorted(
            (
                (
                    abs(correlations[(component, network)]),
                    correlations[(component, network)],
                    component,
                )
                for component in components
            ),
            key=lambda match: (match[0], match[1], match[2]),
            reverse=True,
        )
        best_absolute, best_correlation, best_component = ordered[0]
        if len(ordered) > 1:
            next_absolute, next_correlation, next_component = ordered[1]
            other = [correlation for _, correlation, _ in ordered[1:]]
        else:
            next_absolute, next_correlation, next_component = (
                float("nan"),
                float("nan"),
                "",
            )
            other = []
        rows.append(
            {
                "smith09_map": network,
                "network": label,
                "analysis_priority": priority,
                "best_component": best_component,
                "correlation": f"{best_correlation:.8g}",
                "absolute_correlation": f"{best_absolute:.8g}",
                "sign": (
                    "positive"
                    if best_correlation > 0
                    else "negative"
                    if best_correlation < 0
                    else "zero"
                ),
                "next_component": next_component,
                "next_correlation": f"{next_correlation:.8g}",
                "next_absolute_correlation": f"{next_absolute:.8g}",
                "other_mean": f"{statistics.mean(other):.8g}" if other else "",
                "other_sd": f"{statistics.stdev(other):.8g}" if len(other) > 1 else "",
                "other_min": f"{min(other):.8g}" if other else "",
                "other_max": f"{max(other):.8g}" if other else "",
            }
        )

    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Raw fslcc output")
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        correlations = read_fslcc(args.input)
        components = validate_matrix(correlations)
    except (OSError, ValueError) as error:
        raise SystemExit(f"ERROR: {error}") from error
    args.output_dir.mkdir(parents=True, exist_ok=True)
    matrix = args.output_dir / "smith09_component_correlations.tsv"
    best = args.output_dir / "smith09_best_matches.tsv"
    write_matrix(matrix, correlations, components)
    write_best_matches(best, correlations, components)
    print(f"Components: {len(components)}")
    print(f"Wrote {matrix}")
    print(f"Wrote {best}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
