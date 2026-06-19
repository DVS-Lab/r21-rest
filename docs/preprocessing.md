# Preprocessing Launchers

This repository uses simple Linux launchers for fMRIPrep 25.2.5 and MRIQC
24.0.2. They are designed to match the organization used in the related lab
repositories: one script for one subject, and one `run_*` script for a subject
list.

The scripts do not connect to the Linux server from this machine. Use
`--dry-run` or `--render-only` locally to inspect commands without validating
`/ZPOOL` paths.

## Paths

Default Linux paths:

```bash
PROJECT_ROOT=/ZPOOL/data/projects/r21-rest
BIDS_DIR=/ZPOOL/data/projects/r21-cardgame/bids
DERIVATIVES_ROOT=/ZPOOL/data/projects/r21-rest/derivatives
WORK_ROOT=/ZPOOL/data/scratch/$USER
```

Default outputs:

- fMRIPrep: `derivatives/fmriprep-25.2.5`
- FreeSurfer: `derivatives/freesurfer`
- MRIQC: `derivatives/mriqc`
- logs: `derivatives/logs`

## Preflight

Render the configuration and resource projection:

```bash
code/preflight_linux.sh --render-only
```

On Linux, validate the expected paths, containers, and resource projection:

```bash
code/preflight_linux.sh
```

The preflight script reads `config/linux.env` if present, otherwise
`config/linux.env.example`. The main launchers have the standard Linux defaults
built in and can be overridden with environment variables when needed.

## Participant Discovery

List BIDS participants on Linux:

```bash
code/list_subjects.sh --output code/sublist.txt
```

Participant labels are normalized so `189` and `sub-189` are equivalent.
Comments and blank lines are accepted in subject lists.

## fMRIPrep

Render a one-subject pilot command:

```bash
code/run_fmriprep.sh --pilot-one --dry-run
```

Run a one-subject pilot:

```bash
code/run_fmriprep.sh --pilot-one
```

Run the full list:

```bash
code/run_fmriprep.sh
```

`code/fmriprep.sh` runs one participant. `code/run_fmriprep.sh` reads
`code/sublist.txt` by default and writes one log per subject under
`derivatives/logs/fmriprep`.

fMRIPrep uses:

```bash
--skip-bids-validation
--cifti-output 91k
--output-spaces fsLR MNI152NLin6Asym
--work-dir /scratch
```

## MRIQC

Render a one-subject MRIQC pilot command:

```bash
code/run_mriqc.sh --pilot-one --dry-run
```

Run a one-subject MRIQC pilot:

```bash
code/run_mriqc.sh --pilot-one
```

Run MRIQC for the full list:

```bash
code/run_mriqc.sh
```

Run the group report after participant reports complete:

```bash
code/mriqc_group.sh
```

`code/mriqc.sh` runs one participant. `code/run_mriqc.sh` reads
`code/sublist.txt` by default and writes one log per subject under
`derivatives/logs/mriqc`.

MRIQC uses:

```bash
--modalities T1w bold
--task-id rest
--no-datalad-get
--no-sub
```

This project is not treated as multi-echo data.

## Status Summary

Summarize expected fMRIPrep and MRIQC outputs:

```bash
code/check_preprocessing_status.py --subjects code/sublist.txt
```

Optional machine-readable summaries:

```bash
code/check_preprocessing_status.py \
  --subjects code/sublist.txt \
  --output-csv derivatives/status/preprocessing-summary.csv \
  --output-json derivatives/status/preprocessing-summary.json
```

The status checker looks for fMRIPrep subject HTML, preprocessed BOLD outputs,
fMRIPrep confounds files, and MRIQC participant HTML. Marker columns are kept
for compatibility with older launcher drafts and may remain `missing` with the
simplified scripts.
