"""Post-installation script for Playwright.

This script is executed after the dependencies are installed on Streamlit Cloud.
It ensures that the Chromium browser used by Playwright is downloaded into
a local directory under the project root rather than the default global
location. Storing the browser in the repository folder avoids issues with
read‑only filesystems in the cloud environment.

The environment variable `PLAYWRIGHT_BROWSERS_PATH` is set to `./ms-playwright`
by Streamlit Cloud during deployment. When this variable is defined Playwright
will download its browser bundles into the specified directory instead of
`~/.cache/playwright`.
"""

import os
import subprocess
import sys


def main() -> None:
    """Install the Chromium browser for Playwright.

    On Streamlit Cloud the network may be unreliable or slow; running the
    installation command in a separate process allows retrying if needed.
    """
    # Determine the target directory for Playwright browsers.  This mirrors
    # the setting used in `.streamlit/config.toml` for the `PLAYWRIGHT_BROWSERS_PATH`.
    browsers_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "./ms-playwright")
    os.makedirs(browsers_path, exist_ok=True)

    # Run the install command.  This downloads the Chromium browser package.
    try:
        subprocess.run([
            sys.executable,
            "-m",
            "playwright",
            "install",
            "chromium",
        ], check=True)
    except Exception as exc:
        # If installation fails we surface the error; Streamlit Cloud logs will
        # capture the exception and alert the user to the problem.
        raise RuntimeError("Failed to install Playwright browsers") from exc


if __name__ == "__main__":
    main()