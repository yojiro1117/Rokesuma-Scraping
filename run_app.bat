@echo off
REM Windows batch script to launch the Streamlit application.
REM This file is provided for local development on Windows.

SETLOCAL
IF EXIST "%~dp0venv\Scripts\activate.bat" (
    CALL "%~dp0venv\Scripts\activate.bat"
)

streamlit run "%~dp0app.py" %*
ENDLOCAL