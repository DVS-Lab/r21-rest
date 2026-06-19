# Repository Guidance

This repository contains launchers and support code for the R21 resting-state preprocessing workflow.

## Boundaries

- Do not run fMRIPrep, MRIQC, FSL, containerized neuroimaging jobs, or server-only paths from a Mac workstation.
- Do not connect to the Linux server from automation in this repository.
- Keep derivatives, work directories, container images, FreeSurfer licenses, local configuration, logs, manifests, and status markers out of Git.
- Treat `config/linux.env.example` as documentation and a starting point. Copy it to `config/linux.env` or another untracked path before execution.

## Development Checks

- Shell scripts should pass `bash -n`.
- Python status code should pass `python -m pytest` when test dependencies are available.
- Use `--dry-run` or `--render-only` modes to inspect commands on non-Linux systems.

