#!/usr/bin/env bash

# Simple wrapper script to start the Streamlit application.  It
# delegates to the `streamlit run` command and passes through any
# additional arguments.  Using a shell script makes it trivial to
# launch the app locally during development on Unix-like systems.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Activate the virtual environment if present
if [[ -f "$SCRIPT_DIR/venv/bin/activate" ]]; then
    source "$SCRIPT_DIR/venv/bin/activate"
fi

exec streamlit run "$SCRIPT_DIR/app.py" "$@"