@echo off
REM Batch file to launch the Streamlit application on Windows.
REM Sets the PLAYWRIGHT_BROWSERS_PATH so that Playwright uses the
REM locally downloaded browser binaries.

set PLAYWRIGHT_BROWSERS_PATH=%~dp0\ms-playwright
python -m streamlit run %~dp0app.py
