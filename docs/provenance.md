# Provenance

This repository records the intended software versions, paths, and launch
commands for the R21 resting-state preprocessing workflow.

## Software Targets

- fMRIPrep: 25.2.5
- MRIQC: 24.0.2
- Container runtime: `apptainer` or `singularity`
- Runtime selection: prefer `apptainer` when both runtimes are available
- AFNI: server installation providing `3dBlurToFWHM` and `3dTproject`
- FSL: server installation providing MELODIC, dual regression, and image tools

## fMRIPrep

`code/fmriprep.sh` runs one participant and `code/run_fmriprep.sh` runs a
subject list. The fMRIPrep container receives:

```bash
/input        BIDS input, read-only
/output       project derivatives
/scratch      /ZPOOL/data/scratch/$USER
/opts         FreeSurfer license directory
/opt/templateflow
```

The command uses `--cifti-output 91k`, `--output-spaces fsLR
MNI152NLin6Asym`, and `--work-dir /scratch`.

## MRIQC

`code/mriqc.sh` runs one participant, `code/run_mriqc.sh` runs a subject list,
and `code/mriqc_group.sh` runs the group report. The MRIQC container receives:

```bash
/data         BIDS input, read-only
/out          derivatives/mriqc
/workdir      /ZPOOL/data/scratch/$USER/mriqc/...
/templateflow TemplateFlow cache
/mplconfigdir Matplotlib cache
```

MRIQC uses `--modalities T1w bold`; no multi-echo options are used.

## Resting-State Analysis Inputs

`code/MakeConfounds.py` extracts the 24 extended motion parameters, continuous
FD, six aCompCor components, non-steady-state indicators, and cosine regressors
from each fMRIPrep confounds TSV. Missing initial values are written as zero.

After 5-mm smoothing and masking, `code/regress_confounds.sh` uses one AFNI
`3dTproject` invocation per run with `-ort` for the full nuisance matrix and
`-polort 0` for the constant. `code/check_melodic_inputs.sh` records image,
mask, coverage, intensity, and temporal-variance checks before group MELODIC.
The exact same denoised file list is used for MELODIC and the unmodified FSL
v0.6 `code/dual_regression` script.

`code/run_match_smith09.sh` compares the smoothed/denoised automatic and
fixed-20 ICA solutions with the original Smith09 10-network image. The same
source maps are resampled to the analysis grid for the atlas-based sensitivity
analysis launched by `code/run_dual_regression_smith09.sh`; map order is never
changed.

`code/run_dual_regression.sh` launches the denoised automatic or fixed-20
data-derived ICA solution with design normalization and writes an
`input_order.tsv` beside the FSL outputs. `code/make_dual_regression_contrasts.sh`
uses that table to locate each participant's four conditions, extracts one
requested component from the raw stage-2 coefficient maps, constructs the seven
planned paired differences, and records the participant order used in the
merged `randomise` inputs. Generated one-sample designs include positive and
negative contrasts. `code/randomise.sh` runs one test with 3D TFCE and
cluster-extent inference (`-T -c 3.1`); `code/run_randomise.sh` reads the
committed Smith09 comparison table and launches DMN or all primary-network
tests with at most 24 concurrent processes.

`code/check_randomise_results.py` verifies C1=`1` and C2=`-1`, checks merged
input volume counts, and audits the expected t-stat and corrected-p outputs for
both TFCE and cluster extent. It writes a tracked TSV under
`derivatives/fsl/randomise_summary` and copies complete corrp maps with peak
`1-p > 0.95` into that directory with JSON provenance sidecars.

## Logs

Batch launchers write one timestamped log per subject:

```bash
derivatives/logs/fmriprep/sub-*_YYYYMMDDTHHMMSSZ.log
derivatives/logs/mriqc/sub-*_YYYYMMDDTHHMMSSZ.log
```

The launchers do not remove derivatives, FreeSurfer subjects, or scratch
directories. Failed or incomplete subjects can be rerun, allowing the container
tools to reuse their normal outputs and work directories where supported.
