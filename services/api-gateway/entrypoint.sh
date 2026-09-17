#!/bin/bash
set -e

# In Docker, PYTHONPATH is set by the image (services/api-gateway/src + libs/common/src).
# For running this script outside Docker (e.g. from the service dir directly),
# fall back to the local src/ layout.
export PYTHONPATH="${PYTHONPATH:-$(pwd)/src}"

exec python main.py --log-level "${LOG_LEVEL:-info}"
