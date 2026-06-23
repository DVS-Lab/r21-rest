# Randomise Results Notebook

`plot_randomise_results.ipynb` interactively displays significant
cluster-extent results on an MNI brain and summarizes the corresponding
dual-regression stage-2 beta within the suprathreshold region for sham, RTPJ,
VLPFC, and BOTH.

Run the result checker before opening the notebook:

```bash
python3 code/check_randomise_results.py --analysis-set all --fail-on-missing
jupyter lab notebooks/plot_randomise_results.ipynb
```

The first notebook cell installs any missing Python packages from
`notebooks/requirements.txt` into the active Jupyter kernel. The notebook does
not require FSL or Neurodesk after the randomise and dual-regression outputs
exist.

Only cluster-extent results are displayed. The region is selected from the
same group contrast summarized in the bar plot, so the condition means and
SEM are descriptive and must not be treated as independent ROI inference.
