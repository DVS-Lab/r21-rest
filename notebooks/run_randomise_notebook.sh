#!/usr/bin/env bash
set -euo pipefail

scriptdir="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
projectroot="$(dirname "$scriptdir")"
python_bin="${PYTHON:-python3}"

"$python_bin" -m pip install -r "${scriptdir}/requirements.txt"

echo "Starting JupyterLab with: $python_bin" >&2
echo "Notebook: ${scriptdir}/plot_randomise_results.ipynb" >&2
cd "$projectroot"
exec "$python_bin" -m jupyter lab "${scriptdir}/plot_randomise_results.ipynb"
