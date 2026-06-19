# Repository Guidance

This repository contains launchers and support code for the R21 resting-state preprocessing workflow.

## Boundaries

- Do not run fMRIPrep, MRIQC, FSL, containerized neuroimaging jobs, or server-only paths from a Mac workstation.
- Do not connect to the Linux server from automation in this repository.
- Keep derivatives, work directories, container images, FreeSurfer licenses, and logs out of Git.
- Use the launchers' built-in Linux defaults and environment variables for occasional path overrides.

## Development Checks

- Shell scripts should pass `bash -n`.
- Python code should pass `python -m unittest discover -s tests`.
- Use `--dry-run` or `--render-only` modes to inspect commands on non-Linux systems.
