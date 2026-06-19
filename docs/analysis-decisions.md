# Analysis Decisions

This preprocessing draft is limited to fMRIPrep execution, MRIQC execution, and
completion summaries. It does not implement condition contrasts, smoothing,
MELODIC, network matching, dual regression, or randomise.

## Current Study Context

The resting-state fMRI project includes four within-participant stimulation
conditions:

- `SHAM`: no active stimulation
- `RTPJ`: stimulation at the RTPJ site
- `VLPFC`: stimulation at the VLPFC site
- `BOTH`: simultaneous stimulation at both sites

The project is not currently being treated as a simple 2 x 2 factorial design.

## Deferred Methodological Decisions

- Volumetric data may later receive minimal 4-mm FWHM SUSAN smoothing.
- Surface data would require a separate Connectome Workbench smoothing step.
- Nuisance regression will be incorporated into a modified FSL dual-regression
  procedure.
- fMRIPrep outputs should not be nuisance-regressed during this preprocessing
  assignment.
- Group MELODIC will eventually be run both with fixed dimensionality 20 and
  with automatic dimensionality estimation.
- QA will include motion and MRIQC outlier identification consistent with prior
  lab work, including boxplot/IQR-based flags.
- Automated QA should flag observations rather than silently exclude them.
- Bonferroni correction may eventually be used across the primary inferential
  family.

## Provisional Comparisons for Later Discussion

- `BOTH` versus `SHAM`
- `BOTH` versus the average of `RTPJ` and `VLPFC`
- `RTPJ` versus `VLPFC`

The meaning of "bidirectional" remains unresolved. It may mean two-sided
inference, or it may mean explicit positive and negative directional contrasts.

