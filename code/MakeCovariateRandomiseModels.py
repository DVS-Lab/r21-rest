#!/usr/bin/env python3
"""Prepare covariate-adjusted randomise models from existing contrast images."""

from __future__ import annotations

import argparse
import csv
import math
import re
import shutil
import subprocess
from pathlib import Path


CONTRASTS = (
    "both-minus-sham",
    "both-minus-rtpj",
    "both-minus-vlpfc",
    "rtpj-minus-vlpfc",
    "rtpj-minus-sham",
    "vlpfc-minus-sham",
    "both-minus-mean-rtpj-vlpfc",
)
COVARIATE_ALIASES = {
    "fdmean": "delta_fd_mean",
    "fd_mean": "delta_fd_mean",
    "delta_fd_mean": "delta_fd_mean",
    "blink": "delta_blink_rate_per_min",
    "blinks": "delta_blink_rate_per_min",
    "blink_rate": "delta_blink_rate_per_min",
    "blink_rate_per_min": "delta_blink_rate_per_min",
    "delta_blink_rate_per_min": "delta_blink_rate_per_min",
    "pupil": "delta_mean_pupil_area",
    "mean_pupil_area": "delta_mean_pupil_area",
    "delta_mean_pupil_area": "delta_mean_pupil_area",
}
COVARIATE_LABELS = {
    "delta_fd_mean": "fdmean",
    "delta_blink_rate_per_min": "blink",
    "delta_mean_pupil_area": "pupil",
}
MUTUALLY_EXCLUSIVE_COVARIATES = (
    {"delta_blink_rate_per_min", "delta_mean_pupil_area"},
)


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def write_tsv(path: Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=fieldnames, delimiter="\t", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def parse_contrasts(value: str) -> list[str]:
    if value.strip().lower() == "all":
        return list(CONTRASTS)
    contrasts: list[str] = []
    for item in value.split(","):
        contrast = item.strip()
        if not contrast:
            continue
        if contrast not in CONTRASTS:
            raise ValueError(f"Unknown contrast: {contrast}")
        if contrast in contrasts:
            raise ValueError(f"Duplicate contrast: {contrast}")
        contrasts.append(contrast)
    if not contrasts:
        raise ValueError("At least one contrast is required")
    return contrasts


def parse_covariates(value: str) -> list[str]:
    covariates: list[str] = []
    for item in value.split(","):
        raw = item.strip()
        if not raw:
            continue
        covariate = COVARIATE_ALIASES.get(raw, raw)
        if covariate in covariates:
            raise ValueError(f"Duplicate covariate: {raw}")
        covariates.append(covariate)
    if not covariates:
        raise ValueError("At least one covariate is required")
    for exclusive_set in MUTUALLY_EXCLUSIVE_COVARIATES:
        overlap = exclusive_set.intersection(covariates)
        if len(overlap) > 1:
            labels = sorted(COVARIATE_LABELS[covariate] for covariate in overlap)
            raise ValueError(
                "Do not model these covariates together: " + ",".join(labels)
            )
    return covariates


def model_label(covariates: list[str], explicit: str | None) -> str:
    if explicit:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", explicit):
            raise ValueError("--model-label must contain lowercase letters, numbers, or hyphens")
        return explicit
    labels = [COVARIATE_LABELS.get(covariate, covariate.replace("delta_", "")) for covariate in covariates]
    return "cov-" + "-".join(labels)


def parse_float(value: str | None) -> float | None:
    if value is None:
        return None
    stripped = value.strip()
    if stripped == "" or stripped.lower() in {"n/a", "nan", "none"}:
        return None
    try:
        number = float(stripped)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def read_subject_order(path: Path) -> list[str]:
    rows = read_tsv(path)
    if not rows:
        raise ValueError(f"{path} has no rows")
    required = {"randomise_index", "participant"}
    missing = required.difference(rows[0])
    if missing:
        raise ValueError(f"{path} is missing columns: {sorted(missing)}")
    ordered = sorted(rows, key=lambda row: int(row["randomise_index"]))
    participants = [row["participant"] for row in ordered]
    if len(participants) != len(set(participants)):
        raise ValueError(f"{path} contains duplicate participants")
    return participants


def primary_participants(covariate_rows: dict[tuple[str, str], dict[str, str]]) -> list[str]:
    participants = sorted({participant for participant, _contrast in covariate_rows})
    selected = [
        participant
        for participant in participants
        if all(
            covariate_rows.get((participant, contrast), {}).get("complete", "") == "true"
            for contrast in CONTRASTS
        )
    ]
    if not selected:
        raise ValueError("No participants are complete for the primary contrast family")
    return selected


def load_covariates(path: Path) -> dict[tuple[str, str], dict[str, str]]:
    rows = read_tsv(path)
    if not rows:
        raise ValueError(f"{path} has no rows")
    required = {"participant", "contrast", "complete", "missing_conditions"}
    missing = required.difference(rows[0])
    if missing:
        raise ValueError(f"{path} is missing columns: {sorted(missing)}")
    output: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        row["complete"] = row["complete"].strip().lower()
        key = (row["participant"], row["contrast"])
        if key in output:
            raise ValueError(f"Duplicate covariate row for {key[0]} {key[1]}")
        output[key] = row
    return output


def select_participants(
    base_participants: list[str],
    covariate_rows: dict[tuple[str, str], dict[str, str]],
    contrast: str,
    covariates: list[str],
) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    selected: list[dict[str, object]] = []
    excluded: list[dict[str, str]] = []
    for participant in base_participants:
        row = covariate_rows.get((participant, contrast))
        if row is None:
            excluded.append({"participant": participant, "reason": "missing_covariate_row"})
            continue
        if row["complete"] != "true":
            reason = "incomplete_conditions"
            missing = row.get("missing_conditions", "").strip()
            if missing:
                reason = f"{reason}:{missing}"
            excluded.append({"participant": participant, "reason": reason})
            continue

        raw_values: dict[str, float] = {}
        missing_covariates: list[str] = []
        for covariate in covariates:
            value = parse_float(row.get(covariate))
            if value is None:
                missing_covariates.append(covariate)
            else:
                raw_values[covariate] = value
        if missing_covariates:
            excluded.append(
                {
                    "participant": participant,
                    "reason": "missing_covariate:" + ",".join(missing_covariates),
                }
            )
            continue
        selected.append({"participant": participant, "raw_values": raw_values})
    return selected, excluded


def demean_covariates(
    selected: list[dict[str, object]], covariates: list[str]
) -> tuple[list[dict[str, str]], dict[str, float]]:
    means: dict[str, float] = {}
    for covariate in covariates:
        values = [entry["raw_values"][covariate] for entry in selected]  # type: ignore[index]
        means[covariate] = float(sum(values) / len(values))
        centered = [value - means[covariate] for value in values]
        if max(abs(value) for value in centered) < 1e-12:
            raise ValueError(f"{covariate} has zero variance after demeaning")

    rows: list[dict[str, str]] = []
    for index, entry in enumerate(selected):
        participant = str(entry["participant"])
        raw_values = entry["raw_values"]  # type: ignore[assignment]
        row = {"randomise_index": str(index), "participant": participant}
        for covariate in covariates:
            raw = raw_values[covariate]
            demeaned = raw - means[covariate]
            row[covariate] = f"{raw:.10g}"
            row[f"{covariate}_demeaned"] = f"{demeaned:.10g}"
        rows.append(row)
    return rows, means


def fsl_float(value: float | str) -> str:
    return f"{float(value):.6e}"


def design_ppheights(audit_rows: list[dict[str, str]], covariates: list[str]) -> list[float]:
    heights = [1.0]
    for covariate in covariates:
        column = f"{covariate}_demeaned"
        values = [float(row[column]) for row in audit_rows]
        heights.append(max(values) - min(values))
    return heights


def write_design_mat(path: Path, audit_rows: list[dict[str, str]], covariates: list[str]) -> Path:
    n_participants = len(audit_rows)
    ev_columns = [f"{covariate}_demeaned" for covariate in covariates]
    heights = design_ppheights(audit_rows, covariates)
    with path.open("w") as stream:
        stream.write(f"/NumWaves\t{1 + len(covariates)}\n")
        stream.write(f"/NumPoints\t{n_participants}\n")
        stream.write("/PPheights\t\t" + "\t".join(fsl_float(value) for value in heights) + "\n\n")
        stream.write("/Matrix\n")
        for row in audit_rows:
            values = [1.0, *[float(row[column]) for column in ev_columns]]
            stream.write("\t".join(fsl_float(value) for value in values) + "\n")
    return path


def component_metadata(component_dir: Path) -> tuple[str, str]:
    match = re.search(r"component-(\d+)_stat-([A-Za-z0-9]+)$", component_dir.name)
    if not match:
        raise ValueError(f"Could not infer component/stat label from {component_dir}")
    return match.group(1), match.group(2)


def infer_mask(component_dir: Path) -> Path:
    if component_dir.parent.name != "contrasts":
        raise ValueError(f"Expected component dir under a contrasts directory: {component_dir}")
    return component_dir.parent.parent / "mask.nii.gz"


def source_contrast_image(
    component_dir: Path, task: str, component_padded: str, map_type: str, contrast: str, participant: str
) -> Path:
    return (
        component_dir
        / contrast
        / f"{participant}_task-{task}_component-{component_padded}_stat-{map_type}_contrast-{contrast}.nii.gz"
    )


def write_design_files(
    output_dir: Path, audit_rows: list[dict[str, str]], covariates: list[str]
) -> tuple[Path, Path, Path]:
    n_participants = len(audit_rows)
    n_waves = 1 + len(covariates)

    design_mat = output_dir / "design.mat"
    write_design_mat(design_mat, audit_rows, covariates)

    design_con = output_dir / "design.con"
    with design_con.open("w") as stream:
        stream.write("/ContrastName1\tPositive\n")
        stream.write("/ContrastName2\tNegative\n")
        stream.write(f"/NumWaves\t{n_waves}\n")
        stream.write("/NumContrasts\t2\n")
        stream.write("/PPheights\t1\t1\n")
        stream.write("/RequiredEffect\t1\t1\n\n")
        stream.write("/Matrix\n")
        stream.write("\t".join(["1", *["0"] * len(covariates)]) + "\n")
        stream.write("\t".join(["-1", *["0"] * len(covariates)]) + "\n")

    design_grp = output_dir / "design.grp"
    with design_grp.open("w") as stream:
        stream.write("/NumWaves\t1\n")
        stream.write(f"/NumPoints\t{n_participants}\n\n")
        stream.write("/Matrix\n")
        for _row in audit_rows:
            stream.write("1\n")
    return design_mat, design_con, design_grp


def template_rows(audit_rows: list[dict[str, str]], covariates: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for audit_row in audit_rows:
        row = {"participant": audit_row["participant"], "intercept": "1"}
        for covariate in covariates:
            row[f"{covariate}_demeaned"] = audit_row[f"{covariate}_demeaned"]
        rows.append(row)
    return rows


def write_design_template(
    template_dir: Path,
    task: str,
    label: str,
    contrast: str,
    audit_rows: list[dict[str, str]],
    excluded: list[dict[str, str]],
    covariates: list[str],
) -> dict[str, str]:
    n_participants = len(audit_rows)
    stem = f"task-{task}_model-{label}_contrast-{contrast}_N-{n_participants:02d}_design-template"
    rows = template_rows(audit_rows, covariates)
    fields = ["participant", "intercept", *[f"{covariate}_demeaned" for covariate in covariates]]
    tsv = template_dir / f"{stem}.tsv"
    design_mat = template_dir / f"{stem}.mat"
    write_tsv(tsv, rows, fields)
    write_design_mat(design_mat, audit_rows, covariates)
    excluded_name = ""
    if excluded:
        excluded_path = template_dir / f"{stem}_excluded-participants.tsv"
        write_tsv(excluded_path, excluded, ["participant", "reason"])
        excluded_name = excluded_path.name
    return {
        "model_label": label,
        "contrast": contrast,
        "n_participants": str(n_participants),
        "covariates": ",".join(covariates),
        "template_tsv": tsv.name,
        "template_mat": design_mat.name,
        "excluded_participants_tsv": excluded_name,
    }


def write_template_root_readme(template_root: Path) -> None:
    template_root.mkdir(parents=True, exist_ok=True)
    readme = template_root / "README.md"
    readme.write_text(
        "# Randomise Covariate Templates\n\n"
        "These small spreadsheets mirror the covariate design matrices used for "
        "whole-brain randomise follow-up models. They are tracked in GitHub so the "
        "FSL model setup can be reviewed without copying large derivative images.\n\n"
        "Each model folder contains one FSL `design.mat` template plus one labeled "
        "TSV per contrast. File names "
        "include the analysis task, model label, contrast, and contrast-specific N. "
        "Columns are ordered as `participant`, `intercept`, then demeaned covariates. "
        "The `intercept` column is always `1` and is not demeaned.\n\n"
        "The `.mat` files can be passed directly to FSL. The paired TSV files keep "
        "the same rows labeled for review.\n"
    )


def write_templates(
    template_root: Path,
    task: str,
    label: str,
    contrasts: list[str],
    base_participants: list[str],
    covariate_rows: dict[tuple[str, str], dict[str, str]],
    covariates: list[str],
) -> Path:
    write_template_root_readme(template_root)
    template_dir = template_root / f"model-{label}"
    template_dir.mkdir(parents=True, exist_ok=True)
    for stale_path in template_dir.glob(f"task-{task}_model-{label}_contrast-*_design-template.csv"):
        stale_path.unlink()
    for stale_path in template_dir.glob(
        f"task-{task}_model-{label}_contrast-*_design-template_excluded-participants.tsv"
    ):
        stale_path.unlink()
    manifest_rows: list[dict[str, str]] = []
    for contrast in contrasts:
        selected, excluded = select_participants(base_participants, covariate_rows, contrast, covariates)
        if len(selected) <= 1 + len(covariates):
            raise ValueError(
                f"{contrast}: N={len(selected)} is too small for {1 + len(covariates)} EVs"
            )
        audit_rows, _means = demean_covariates(selected, covariates)
        manifest_rows.append(
            write_design_template(template_dir, task, label, contrast, audit_rows, excluded, covariates)
        )
    manifest = template_dir / f"task-{task}_model-{label}_design-template_manifest.tsv"
    write_tsv(
        manifest,
        manifest_rows,
        [
            "model_label",
            "contrast",
            "n_participants",
            "covariates",
            "template_tsv",
            "template_mat",
            "excluded_participants_tsv",
        ],
    )
    readme = template_dir / "README.md"
    readme.write_text(
        "# Randomise Covariate Design Templates\n\n"
        f"Model: `{label}`\n\n"
        f"Task: `{task}`\n\n"
        "Each `.mat` file is ready for FSL. The paired TSV carries the same rows "
        "with labels and is ordered as `participant`, `intercept`, then demeaned "
        "covariates. The intercept column is intentionally not demeaned. File names "
        "include the contrast-specific N.\n\n"
        "An `_excluded-participants.tsv` file is written only when participants were "
        "dropped from that contrast because a required covariate was unavailable.\n"
    )
    return manifest


def template_participants(
    covariate_rows: dict[tuple[str, str], dict[str, str]], subject_order: Path | None
) -> list[str]:
    if subject_order:
        return read_subject_order(subject_order.resolve())
    return primary_participants(covariate_rows)


def build_run_randomise_script(
    model_dir: Path,
    jobs: list[dict[str, str]],
    mask: Path,
    n_perm: int,
    cluster_threshold: float,
    tfce: bool,
) -> Path:
    script = model_dir / "run_randomise.sh"
    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "",
        f'nperm="${{N_PERM:-{n_perm}}}"',
        f'cluster_threshold="${{CLUSTER_THRESHOLD:-{cluster_threshold:g}}}"',
        "tfce_args=()",
        f'[[ "${{TFCE:-{1 if tfce else 0}}}" == "1" ]] && tfce_args=(-T)',
        "command -v randomise >/dev/null 2>&1 || { echo \"ERROR: randomise is not on PATH.\" >&2; exit 1; }",
        "",
    ]
    for job in jobs:
        output_prefix = Path(job["output_prefix"])
        lines.extend(
            [
                f'mkdir -p {shlex_quote(str(output_prefix.parent))}',
                f'complete={shlex_quote(str(output_prefix))}.complete',
                'if [[ -f "$complete" ]]; then',
                f'    echo "Already complete: {output_prefix}" >&2',
                "else",
                "    cmd=(",
                "        randomise",
                f'        -i {shlex_quote(job["group_input"])}',
                f'        -o {shlex_quote(str(output_prefix))}',
                f'        -m {shlex_quote(str(mask))}',
                f'        -d {shlex_quote(job["design_mat"])}',
                f'        -t {shlex_quote(job["design_con"])}',
                '        -n "$nperm" "${tfce_args[@]}" -c "$cluster_threshold"',
                "    )",
                '    "${cmd[@]}"',
                '    date -u +%Y-%m-%dT%H:%M:%SZ >"$complete"',
                "fi",
                "",
            ]
        )
    script.write_text("\n".join(lines))
    script.chmod(0o755)
    return script


def shlex_quote(value: str) -> str:
    return "'" + value.replace("'", "'\\''") + "'"


def load_summary_jobs(summary_paths: list[Path], significant_only: bool) -> dict[Path, dict[str, set[str] | set[tuple[str, str]]]]:
    jobs: dict[Path, dict[str, set[str] | set[tuple[str, str]]]] = {}
    for path in summary_paths:
        for row in read_tsv(path):
            if row.get("inference") != "cluster-extent" or row.get("status") != "ok":
                continue
            if significant_only and row.get("peak_gt_threshold") != "true":
                continue
            corrp = row.get("corrp_file", "").strip()
            if not corrp:
                continue
            corrp_path = Path(corrp)
            parts = corrp_path.parts
            if "randomise" not in parts:
                raise ValueError(f"Could not infer component dir from {corrp}")
            component_dir = Path(*parts[: parts.index("randomise")])
            contrast = row["condition_contrast"]
            network = row.get("network", "network") or "network"
            entry = jobs.setdefault(component_dir, {"contrasts": set(), "networks": set()})
            entry["contrasts"].add(contrast)  # type: ignore[union-attr]
            entry["networks"].add((contrast, network))  # type: ignore[union-attr]
    return jobs


def write_model(
    component_dir: Path,
    contrasts: list[str],
    network_jobs: set[tuple[str, str]],
    covariate_rows: dict[tuple[str, str], dict[str, str]],
    covariates: list[str],
    label: str,
    task: str,
    output_subdir: str,
    mask: Path | None,
    n_perm: int,
    cluster_threshold: float,
    tfce: bool,
    skip_merge: bool,
    overwrite: bool,
    dry_run: bool,
) -> Path:
    source_component_dir = component_dir.resolve()
    component_padded, map_type = component_metadata(source_component_dir)
    model_dir = source_component_dir / output_subdir / f"model-{label}"

    print(f"Component: {source_component_dir}")
    print(f"Model: {model_dir}")
    print(f"Component volume: {component_padded}; map type: {map_type}")
    print(f"Contrasts: {','.join(contrasts)}")
    if dry_run:
        return model_dir

    subject_order = source_component_dir / "subject_order.tsv"
    base_participants = read_subject_order(subject_order)
    mask_path = mask.resolve() if mask else infer_mask(source_component_dir)
    print(f"Base participants: {len(base_participants)}")
    if model_dir.exists() and not overwrite:
        raise ValueError(f"Output already exists: {model_dir}")
    model_dir.mkdir(parents=True, exist_ok=True)

    manifest_rows: list[dict[str, str]] = []
    randomise_jobs: list[dict[str, str]] = []
    fslmerge = shutil.which("fslmerge")
    if not skip_merge and fslmerge is None:
        raise ValueError("fslmerge is not on PATH; rerun with --skip-merge to write designs only")

    for contrast in contrasts:
        selected, excluded = select_participants(base_participants, covariate_rows, contrast, covariates)
        n_waves = 1 + len(covariates)
        if len(selected) <= n_waves:
            raise ValueError(
                f"{source_component_dir} {contrast}: N={len(selected)} is too small for {n_waves} EVs"
            )
        audit_rows, means = demean_covariates(selected, covariates)
        contrast_dir = model_dir / contrast
        contrast_dir.mkdir(parents=True, exist_ok=True)

        selected_rows = [
            {"randomise_index": row["randomise_index"], "participant": row["participant"]}
            for row in audit_rows
        ]
        write_tsv(contrast_dir / "subject_order.tsv", selected_rows, ["randomise_index", "participant"])
        write_tsv(contrast_dir / "excluded_participants.tsv", excluded, ["participant", "reason"])
        audit_fields = ["randomise_index", "participant"]
        for covariate in covariates:
            audit_fields.extend([covariate, f"{covariate}_demeaned"])
        write_tsv(contrast_dir / "covariate_audit.tsv", audit_rows, audit_fields)
        design_mat, design_con, design_grp = write_design_files(contrast_dir, audit_rows, covariates)

        image_paths = [
            source_contrast_image(
                source_component_dir, task, component_padded, map_type, contrast, str(entry["participant"])
            )
            for entry in selected
        ]
        image_list = contrast_dir / "image_list.txt"
        image_list.write_text("\n".join(str(path) for path in image_paths) + "\n")
        missing_images = [path for path in image_paths if not path.is_file()]
        if missing_images and not skip_merge:
            raise ValueError(
                f"{source_component_dir} {contrast}: missing source images, first missing: {missing_images[0]}"
            )
        group_input = (
            contrast_dir
            / f"group_task-{task}_component-{component_padded}_stat-{map_type}_contrast-{contrast}_model-{label}.nii.gz"
        )
        if not skip_merge:
            subprocess.run([fslmerge, "-t", str(group_input), *map(str, image_paths)], check=True)

        covariate_mean_text = ";".join(f"{covariate}={means[covariate]:.10g}" for covariate in covariates)
        manifest_rows.append(
            {
                "component_dir": str(source_component_dir),
                "model_dir": str(model_dir),
                "contrast": contrast,
                "n_participants": str(len(selected)),
                "n_excluded": str(len(excluded)),
                "covariates": ",".join(covariates),
                "covariate_means": covariate_mean_text,
                "group_input": str(group_input),
                "design_mat": str(design_mat),
                "design_con": str(design_con),
                "design_grp": str(design_grp),
            }
        )

        networks = sorted(network for item_contrast, network in network_jobs if item_contrast == contrast)
        if not networks:
            networks = ["covariate"]
        for network in networks:
            output_prefix = (
                model_dir
                / "randomise"
                / f"network-{network}"
                / f"task-{task}_network-{network}_component-{component_padded}_stat-{map_type}_contrast-{contrast}_model-{label}"
            )
            randomise_jobs.append(
                {
                    "contrast": contrast,
                    "network": network,
                    "group_input": str(group_input),
                    "design_mat": str(design_mat),
                    "design_con": str(design_con),
                    "design_grp": str(design_grp),
                    "output_prefix": str(output_prefix),
                }
            )

    manifest_path = model_dir / "model_manifest.tsv"
    write_tsv(
        manifest_path,
        manifest_rows,
        [
            "component_dir",
            "model_dir",
            "contrast",
            "n_participants",
            "n_excluded",
            "covariates",
            "covariate_means",
            "group_input",
            "design_mat",
            "design_con",
            "design_grp",
        ],
    )
    write_tsv(
        model_dir / "randomise_jobs.tsv",
        randomise_jobs,
        ["contrast", "network", "group_input", "design_mat", "design_con", "design_grp", "output_prefix"],
    )
    run_script = build_run_randomise_script(
        model_dir, randomise_jobs, mask_path, n_perm, cluster_threshold, tfce
    )
    readme = model_dir / "README.md"
    readme.write_text(
        "# Covariate Randomise Model\n\n"
        f"Source component: `{source_component_dir}`\n\n"
        f"Covariates: `{', '.join(covariates)}`\n\n"
        "Each contrast has its own participant order, design files, and merged group image. "
        "This is necessary because pupil data are missing for a small number of condition runs.\n\n"
        f"Run with: `{run_script}`\n"
    )
    print(f"Wrote {manifest_path}")
    print(f"Next: {run_script}")
    return model_dir


def parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).resolve().parents[1]
    fsl_dir = repo_root / "derivatives" / "fsl"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--component-dir",
        type=Path,
        action="append",
        help="Existing component-XXXX_stat-beta contrast directory. May be repeated.",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        action="append",
        help="Randomise peak summary TSV; significant cluster-extent rows define follow-up jobs.",
    )
    parser.add_argument(
        "--include-nonsignificant",
        action="store_true",
        help="When using --summary, include all ok cluster-extent rows instead of significant rows only.",
    )
    parser.add_argument(
        "--group-covariates",
        type=Path,
        default=repo_root / "derivatives" / "qc" / "task-rest_group_covariates.tsv",
    )
    parser.add_argument("--covariates", default="fdmean,blink")
    parser.add_argument("--model-label")
    parser.add_argument("--contrasts", default="all")
    parser.add_argument("--task", default="rest")
    parser.add_argument("--output-subdir", default="covariate-models")
    parser.add_argument(
        "--template-dir",
        type=Path,
        default=repo_root / "templates" / "randomise_covariate_models",
        help="Tracked root folder for small design.mat templates and labeled TSVs.",
    )
    parser.add_argument(
        "--template-subject-order",
        type=Path,
        help="Optional subject_order.tsv to define the template participant pool.",
    )
    parser.add_argument(
        "--templates-only",
        action="store_true",
        help="Only write design template spreadsheets; do not build component model folders.",
    )
    parser.add_argument(
        "--no-templates",
        action="store_true",
        help="Do not write root-level template spreadsheets during model setup.",
    )
    parser.add_argument("--mask", type=Path)
    parser.add_argument("--n-perm", type=int, default=5000)
    parser.add_argument("--cluster-threshold", type=float, default=3.1)
    parser.add_argument("--tfce", action="store_true")
    parser.add_argument("--skip-merge", action="store_true", help="Write designs and image lists without calling fslmerge.")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.set_defaults(
        summary_default=[
            fsl_dir / "randomise_summary" / "task-rest_randomise_peak_summary.tsv",
            fsl_dir / "randomise_summary" / "task-rest_desc-SecondaryNetworks_randomise_peak_summary.tsv",
        ]
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    covariates = parse_covariates(args.covariates)
    label = model_label(covariates, args.model_label)
    covariate_rows = load_covariates(args.group_covariates.resolve())
    base_template_participants = template_participants(covariate_rows, args.template_subject_order)

    if args.templates_only:
        contrasts = parse_contrasts(args.contrasts)
        manifest = write_templates(
            args.template_dir.resolve(),
            args.task,
            label,
            contrasts,
            base_template_participants,
            covariate_rows,
            covariates,
        )
        print(f"Model label: {label}")
        print(f"Covariates: {','.join(covariates)}")
        print(f"Template participants: {len(base_template_participants)}")
        print(f"Wrote {manifest}")
        return 0

    component_jobs: dict[Path, dict[str, set[str] | set[tuple[str, str]]]] = {}
    if args.summary:
        component_jobs = load_summary_jobs(
            [path.resolve() for path in args.summary], not args.include_nonsignificant
        )
    elif args.component_dir:
        contrasts = set(parse_contrasts(args.contrasts))
        component_jobs = {
            path.resolve(): {"contrasts": set(contrasts), "networks": set()}
            for path in args.component_dir
        }
    else:
        existing_summaries = [path for path in args.summary_default if path.is_file()]
        if not existing_summaries:
            raise ValueError("Provide --component-dir or --summary")
        component_jobs = load_summary_jobs(
            existing_summaries, significant_only=not args.include_nonsignificant
        )

    if not component_jobs:
        raise ValueError("No covariate randomise models to prepare")

    print(f"Model label: {label}")
    print(f"Covariates: {','.join(covariates)}")
    print(f"Components: {len(component_jobs)}")
    if not args.no_templates and not args.dry_run:
        template_contrasts = sorted(
            {
                contrast
                for job_info in component_jobs.values()
                for contrast in job_info["contrasts"]  # type: ignore[union-attr]
            },
            key=list(CONTRASTS).index,
        )
        manifest = write_templates(
            args.template_dir.resolve(),
            args.task,
            label,
            template_contrasts,
            base_template_participants,
            covariate_rows,
            covariates,
        )
        print(f"Wrote design templates: {manifest}")
    for component_dir, job_info in sorted(component_jobs.items()):
        write_model(
            component_dir=component_dir,
            contrasts=sorted(job_info["contrasts"], key=list(CONTRASTS).index),  # type: ignore[arg-type]
            network_jobs=job_info["networks"],  # type: ignore[arg-type]
            covariate_rows=covariate_rows,
            covariates=covariates,
            label=label,
            task=args.task,
            output_subdir=args.output_subdir,
            mask=args.mask,
            n_perm=args.n_perm,
            cluster_threshold=args.cluster_threshold,
            tfce=args.tfce,
            skip_merge=args.skip_merge,
            overwrite=args.overwrite,
            dry_run=args.dry_run,
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"ERROR: {error}")
        raise SystemExit(1)
