# Provenance

This draft records commands and execution state so preprocessing can be audited
after running on Linux.

## Software Targets

- fMRIPrep: 25.2.5
- MRIQC: 24.0.2
- Container runtime: `apptainer` or `singularity`
- Runtime selection: `CONTAINER_RUNTIME="auto"` prefers `apptainer` when both
  runtimes are available.
- fMRIPrep work directory: host `/ZPOOL/data/scratch/$USER`, mounted as
  `/scratch` inside the container.
- fMRIPrep output spaces: `fsLR fsaverage MNI152NLin6Asym MNI152NLin2009cAsym`
  with `--cifti-output 91k`.

The scripts are written and syntax-tested on a Mac, but execution mode is
restricted to Linux. Dry-run/render-only modes deliberately avoid validating
server-only paths such as `/ZPOOL`.

## Recorded Artifacts

Each participant launcher writes:

- a timestamped shell-quoted command file under `MANIFEST_ROOT`
- timestamped stdout and stderr logs under `LOG_ROOT`
- status markers under `STATUS_ROOT`

Running markers include the host and process ID. When a launcher sees an
existing running marker, it checks whether the process appears active on the
same host. Active runs are left alone; stale running markers are archived before
restart.

## Resume Behavior

The launchers do not remove fMRIPrep, MRIQC, FreeSurfer, or work directories.
Participants with complete status markers are skipped unless `--force` is used.
Incomplete participants can be restarted, allowing fMRIPrep and MRIQC to reuse
their normal output and work directories where supported.

## Resource Accounting

Batch launchers calculate projected CPU and memory use from configured jobs,
per-job processes, and per-job memory. Execution mode reports available Linux
CPUs and memory and refuses obvious oversubscription unless
`--allow-oversubscribe` is supplied.
