# r21-rest

Code for preprocessing, quality assessment, and later dual-regression analyses
of resting-state stimulation data from the R21 grant.

The current draft focuses on Linux launchers for fMRIPrep 25.2.5 and MRIQC
24.0.2. The scripts are configuration-driven, render transparent container
commands, write logs/manifests/status markers, and avoid deleting work
directories so incomplete fMRIPrep work can be resumed.

Execution mode is intended for the Linux server only. On a Mac or other review
machine, use `--dry-run` or `--render-only`.

## Quick Start

Use these steps on the Linux server after pulling the branch.

1. Create a local configuration file:

   ```bash
   cp config/linux.env.example config/linux.env
   ```

2. Edit `config/linux.env` and confirm every path and resource setting. The
   example defaults assume:

   - BIDS input: `/ZPOOL/data/projects/r21-cardgame/bids`
   - fMRIPrep image: `/ZPOOL/data/tools/fmriprep-25.2.5.sif`
   - MRIQC image: `/ZPOOL/data/tools/mriqc-24.0.2.sif`
   - derivatives root: `/ZPOOL/data/projects/r21-cardgame/derivatives/r21-rest`
   - scratch root: `/ZPOOL/data/scratch/${USER}/r21-rest`

3. Run a render-only preflight:

   ```bash
   code/preflight_linux.sh --config config/linux.env --render-only
   ```

4. Run the Linux preflight. This validates paths/runtime and checks projected
   resources without launching fMRIPrep or MRIQC:

   ```bash
   code/preflight_linux.sh --config config/linux.env
   ```

5. List BIDS participants:

   ```bash
   code/list_subjects.sh --config config/linux.env --output subjects.txt
   ```

6. Render a one-subject fMRIPrep pilot command:

   ```bash
   code/run_fmriprep_batch.sh --config config/linux.env --subjects subjects.txt --pilot-one --dry-run
   ```

7. Launch one fMRIPrep pilot participant:

   ```bash
   code/run_fmriprep_batch.sh --config config/linux.env --subjects subjects.txt --pilot-one
   ```

8. If the pilot looks good, launch the fMRIPrep batch. Run this inside `tmux`,
   `screen`, or another persistent shell session:

   ```bash
   code/run_fmriprep_batch.sh --config config/linux.env --subjects subjects.txt
   ```

9. Summarize fMRIPrep/MRIQC completion at any point:

   ```bash
   code/check_preprocessing_status.py --config config/linux.env --subjects subjects.txt
   ```

10. Render MRIQC participant commands:

   ```bash
   code/run_mriqc_batch.sh --config config/linux.env --subjects subjects.txt --dry-run
   ```

11. Run MRIQC participant jobs:

   ```bash
   code/run_mriqc_batch.sh --config config/linux.env --subjects subjects.txt
   ```

12. After participant-level MRIQC completes, run the MRIQC group report:

   ```bash
   code/run_mriqc_group.sh --config config/linux.env
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
code/run_fmriprep_batch.sh --config config/linux.env --subjects subjects.txt --max-jobs 5
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
