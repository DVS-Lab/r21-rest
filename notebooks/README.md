# Randomise Results Notebook

`plot_randomise_results.ipynb` displays every significant cluster-extent
result in its own interactive NiiVue MNI viewer. Each result includes a plain-
language description of the analysis, network, signed contrast, corrected
peak p-value, and cluster size, followed by sham, RTPJ, VLPFC, and BOTH
dual-regression stage-2 beta means with SEM.

Run the result checker before opening the notebook. Then close any existing
JupyterLab server and use the project launcher:

```bash
python3 code/check_randomise_results.py --analysis-set all --fail-on-missing
bash notebooks/run_randomise_notebook.sh
```

The result checker uses the Linux-side dual-regression images to write compact
participant-by-condition `*_timeseries.tsv` files beside each significant map.
Commit those TSVs with the updated summary, NIfTI maps, and JSON sidecars. The
notebook reads only these tracked files and therefore does not require the
large dual-regression directories, FSL, or Neurodesk on another computer.

The launcher installs `notebooks/requirements.txt` before starting JupyterLab.
This ordering is required because IPyNiiVue uses AnyWidget in both the Python
kernel and the JupyterLab browser frontend. Installing from a cell in an
already-running Lab session can leave the frontend unregistered. If Lab was
already open during installation, stop it with `Ctrl-C`, rerun the launcher,
and refresh the browser tab.

Only cluster-extent results are displayed. The region is selected from the
same group contrast summarized in the bar plot, so the condition means and
SEM are descriptive and must not be treated as independent ROI inference.
