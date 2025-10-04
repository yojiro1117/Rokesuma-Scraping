@echo off
REM Script to run all smoke tests in one go.
REM You must have pytest installed in your environment.  This script is
REM intended for Windows developers to quickly verify that basic scraping
REM works across several representative locations.

SETLOCAL
pytest -q tests\test_smoke_fukuoka.py tests\test_smoke_tokyo.py tests\test_smoke_osaka.py
ENDLOCAL
