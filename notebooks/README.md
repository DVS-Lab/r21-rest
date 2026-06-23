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

The result checker uses the Linux-side dual-regression images to write compact
participant-by-condition `*_timeseries.tsv` files beside each significant map.
Commit those TSVs with the updated summary, NIfTI maps, and JSON sidecars. The
notebook reads only these tracked files and therefore does not require the
large dual-regression directories, FSL, or Neurodesk on another computer.

The first notebook cell installs any missing Python packages from
`notebooks/requirements.txt` into the active Jupyter kernel.

Only cluster-extent results are displayed. The region is selected from the
same group contrast summarized in the bar plot, so the condition means and
SEM are descriptive and must not be treated as independent ROI inference.
