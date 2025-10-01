"""Post installation script to fetch Playwright browser binaries.

Running this script will download the Chromium browser required by
Playwright into the local project directory.  It honours the
PLAYWRIGHT_BROWSERS_PATH environment variable which is set to
`./ms-playwright` by default in run scripts.  Without running this
installation step the scraper will fail to launch a browser.

Usage
-----
    python postinstall_playwright.py

If the download fails due to network issues, re-run the script once
connectivity has been restored.  The script is idempotent: if the
browsers are already present no action is taken.
"""

import os
import subprocess
import sys



def main() -> None:
    # Determine the path where browsers will be stored
    browsers_path = os.environ.get(
        "PLAYWRIGHT_BROWSERS_PATH", os.path.join(os.path.dirname(__file__), "ms-playwright")
    )
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = browsers_path
    print(f"Installing Playwright browsers into {browsers_path}…")
    try:
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
        print("Playwright installation completed successfully.")
    except subprocess.CalledProcessError as exc:
        print("Playwright installation failed.")
        print(exc)
        sys.exit(exc.returncode)


if __name__ == "__main__":
    main()
