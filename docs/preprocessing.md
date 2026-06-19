# Preprocessing Launchers

This repository provides a draft Linux launcher set for fMRIPrep 25.2.5 and
MRIQC 24.0.2. The scripts are intended to be reviewed on a Mac with
`--dry-run` or `--render-only`, then executed later on the Linux server after
paths, containers, FreeSurfer licensing, and host resources are confirmed.

The scripts do not connect to the Linux server and do not inspect `/ZPOOL` from
the Mac.

## Configuration

Copy the tracked example configuration to an untracked local file:

```bash
cp config/linux.env.example config/linux.env
```

Review every path and resource value in `config/linux.env` before execution.
The defaults are examples for the intended Linux layout:

- BIDS input: `/ZPOOL/data/projects/r21-cardgame/bids`
- fMRIPrep image: `/ZPOOL/data/tools/fmriprep-25.2.5.sif`
- MRIQC image: `/ZPOOL/data/tools/mriqc-24.0.2.sif`
- derivatives root: `/ZPOOL/data/projects/r21-cardgame/derivatives/r21-rest`
- scratch root: `/ZPOOL/data/scratch/${USER}/r21-rest`

Do not commit the local configuration, derivatives, work directories, logs,
manifests, status markers, container images, or FreeSurfer license.

## Preflight

Render configuration and projected resources without validating Linux paths:

```bash
code/preflight_linux.sh --config config/linux.env --render-only
```

On Linux, validate required paths, runtime availability, and projected resources:

```bash
code/preflight_linux.sh --config config/linux.env
```

The default fMRIPrep batch projection is four concurrent jobs with eight
processes and 24 GB memory per job, for a projected maximum of 32 CPU threads
and 96 GB memory. These settings must be compared with the Linux host before
execution. The scripts warn on oversubscription and refuse obvious
oversubscription unless `--allow-oversubscribe` is supplied.

## Participant Discovery

List BIDS participants on Linux:

```bash
code/list_subjects.sh --config config/linux.env --output subjects.txt
```

Participant labels are normalized so `189` and `sub-189` are treated as the same
participant. Comments and blank lines are accepted in subject files.

## fMRIPrep

Render a one-subject pilot command:

```bash
code/run_fmriprep_batch.sh \
  --config config/linux.env \
  --subjects subjects.txt \
  --pilot-one \
  --dry-run
```

Run a one-subject pilot on Linux:

```bash
code/run_fmriprep_batch.sh \
  --config config/linux.env \
  --subjects subjects.txt \
  --pilot-one
```

Run the configured batch:

```bash
code/run_fmriprep_batch.sh --config config/linux.env --subjects subjects.txt
```

Use `--max-jobs 5` only as an explicit override after checking the host. Five
jobs are not assumed safe merely because the flag was requested; resource checks
still apply.

The fMRIPrep subject launcher writes a shell-quoted command manifest, stdout
log, stderr log, and status marker. It skips participants with an existing
complete marker unless `--force` is supplied. It never deletes work directories,
allowing fMRIPrep to resume incomplete work through its normal work directory
behavior.

## MRIQC

Render participant-level MRIQC commands:

```bash
code/run_mriqc_batch.sh --config config/linux.env --subjects subjects.txt --dry-run
```

Run participant-level MRIQC on Linux:

```bash
code/run_mriqc_batch.sh --config config/linux.env --subjects subjects.txt
```

Run group-level MRIQC reporting after participant-level MRIQC completes:

```bash
code/run_mriqc_group.sh --config config/linux.env
```

MRIQC uses the modalities listed in `MRIQC_MODALITIES`, which defaults to
`T1w T2w bold`.

## Status Summary

Summarize expected fMRIPrep and MRIQC outputs:

```bash
code/check_preprocessing_status.py --config config/linux.env --subjects subjects.txt
```

Optional machine-readable summaries:

```bash
code/check_preprocessing_status.py \
  --config config/linux.env \
  --subjects subjects.txt \
  --output-csv status/preprocessing-summary.csv \
  --output-json status/preprocessing-summary.json
```

The status checker looks for participant status markers, fMRIPrep subject HTML,
preprocessed BOLD outputs, fMRIPrep confounds files, and MRIQC participant HTML.
Missing outputs are flagged for review; they are not silently excluded.

