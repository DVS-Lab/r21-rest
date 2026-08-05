#!/usr/bin/env bash
set -euo pipefail

# Compatibility wrapper; new PPI analyses use the 11-map Smith09-plus-reward run.

scriptdir="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
exec bash "${scriptdir}/run_smith09_ppi.sh" dmn-ecn "$@"
