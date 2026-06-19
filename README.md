# r21-rest

Code for preprocessing, quality assessment, and later dual-regression analyses
of resting-state stimulation data from the R21 grant.

The current draft focuses on Linux launchers for fMRIPrep 25.2.5 and MRIQC
24.0.2. The fMRIPrep scripts follow the lab pattern used in related projects:
`code/fmriprep.sh` runs one subject, and `code/run_fmriprep.sh` loops over a
simple subject list with bounded concurrency.

Execution mode is intended for the Linux server only. On a Mac or other review
machine, use `--dry-run` or `--render-only`.

## Quick Start

Use these steps on the Linux server after pulling the branch.

1. Check the defaults:

   ```bash
   code/preflight_linux.sh --render-only
   ```

   The scripts default to `config/linux.env` if it exists, otherwise
   `config/linux.env.example`.

2. The tracked defaults assume:

   - project root: `/ZPOOL/data/projects/r21-rest`
   - BIDS input: `/ZPOOL/data/projects/r21-cardgame/bids`
   - fMRIPrep image: `/ZPOOL/data/tools/fmriprep-25.2.5.sif`
   - MRIQC image: `/ZPOOL/data/tools/mriqc-24.0.2.sif`
   - derivatives root: `/ZPOOL/data/projects/r21-rest/derivatives`
   - scratch/work root: `/ZPOOL/data/scratch/$USER`
   - fMRIPrep output spaces: `fsLR fsaverage MNI152NLin6Asym MNI152NLin2009cAsym`
   - CIFTI output: `91k`

   If any of those differ on the Linux server, copy the example to
   `config/linux.env` and edit only the values that differ:

   ```bash
   cp config/linux.env.example config/linux.env
   ```

3. Run the Linux preflight. This validates paths/runtime and checks projected
   resources without launching fMRIPrep or MRIQC:

   ```bash
   code/preflight_linux.sh
   ```

4. List BIDS participants:

   ```bash
   code/list_subjects.sh --output code/sublist.txt
   ```

5. Render a one-subject fMRIPrep pilot command:

   ```bash
   code/run_fmriprep.sh --pilot-one --dry-run
   ```

6. Launch one fMRIPrep pilot participant:

   ```bash
   code/run_fmriprep.sh --pilot-one
   ```

   The default fMRIPrep command includes `--skip-bids-validation` because the
   source BIDS dataset may not pass the bundled validator cleanly. BIDS issues
   should be reviewed separately; this setting keeps preprocessing from stopping
   before fMRIPrep starts.

   It also uses the lab-standard container layout: BIDS is mounted at `/input`,
   derivatives at `/output`, scratch at `/scratch`, the FreeSurfer license at
   `/opts`, and TemplateFlow at `/opt/templateflow`. fMRIPrep receives
   `--work-dir /scratch`, `--cifti-output 91k`, and
   `--output-spaces fsLR fsaverage MNI152NLin6Asym MNI152NLin2009cAsym`.

7. If the pilot looks good, launch the fMRIPrep batch. Run this inside `tmux`,
   `screen`, or another persistent shell session:

   ```bash
   code/run_fmriprep.sh
   ```

8. Summarize fMRIPrep/MRIQC completion at any point:

   ```bash
   code/check_preprocessing_status.py --subjects code/sublist.txt
   ```

9. Render MRIQC participant commands:

   ```bash
   code/run_mriqc_batch.sh --subjects subjects.txt --dry-run
   ```

10. Run MRIQC participant jobs:

   ```bash
   code/run_mriqc_batch.sh --subjects subjects.txt
   ```

11. After participant-level MRIQC completes, run the MRIQC group report:

   ```bash
   code/run_mriqc_group.sh
   ```

## Resource Defaults

The example configuration uses cautious editable defaults:

```bash
FMRIPREP_MAX_JOBS=4
FMRIPREP_NPROCS=8
FMRIPREP_OMP_NTHREADS=4
FMRIPREP_MEM_MB=24000

MRIQC_MAX_JOBS=4
MRIQC_NPROCS=8
MRIQC_OMP_NTHREADS=4
MRIQC_MEM_GB=12
```

For fMRIPrep, that projects to 32 CPU threads and 96 GB memory at four
concurrent jobs. Compare these values against the Linux host before execution.
The batch scripts report projected resources, report available Linux CPU/memory,
and refuse obvious oversubscription unless `--allow-oversubscribe` is supplied.

`--max-jobs 5` is allowed only as an explicit override:

```bash
code/run_fmriprep.sh --max-jobs 5
```

Five jobs are not assumed safe just because they were requested; resource checks
still apply.

## Outputs

Generated derivatives, work directories, logs, manifests, status markers,
container images, and local configuration files are intentionally untracked.
The relevant configurable roots are:

- `FMRIPREP_OUTPUT_DIR`
- `MRIQC_OUTPUT_DIR`
- `FS_SUBJECTS_DIR`
- `WORK_ROOT`
- `LOG_ROOT`
- `MANIFEST_ROOT`
- `STATUS_ROOT`

See `docs/preprocessing.md` for operational details and
`docs/analysis-decisions.md` for decisions intentionally deferred beyond this
preprocessing assignment.
