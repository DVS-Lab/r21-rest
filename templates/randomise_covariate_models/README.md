# Randomise Covariate Templates

These small spreadsheets mirror the covariate design matrices used for whole-brain randomise follow-up models. They are tracked in GitHub so the FSL GLM GUI setup can be reviewed without copying large derivative images.

Each model folder contains one TSV and one CSV per contrast. File names include the analysis task, model label, contrast, and contrast-specific N. Columns are ordered as `participant`, `intercept`, then demeaned covariates. The `intercept` column is always `1` and is not demeaned.

Use the numeric columns after `participant` as the EV columns in FSL. The positive group contrast is `[1 0 ...]`; the negative group contrast is `[-1 0 ...]`; all participants are in exchangeability group `1`.
