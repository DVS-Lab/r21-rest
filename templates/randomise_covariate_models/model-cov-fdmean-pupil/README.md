# Randomise Covariate Design Templates

Model: `cov-fdmean-pupil`

Task: `rest`

Each `.mat` file is ready for FSL. The paired TSV carries the same rows with labels and is ordered as `participant`, `intercept`, then demeaned covariates. The intercept column is intentionally not demeaned. File names include the contrast-specific N.

An `_excluded-participants.tsv` file is written only when participants were dropped from that contrast because a required covariate was unavailable.
