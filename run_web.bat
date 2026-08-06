@echo off
rem Launch the job assistant web UI (ADK web)
rem Usage: run_web.bat [port]
cd /d %~dp0
set PYTHONPATH=src
set PORT=8000
if not "%~1"=="" set PORT=%~1
echo Starting ADK web UI at http://127.0.0.1:%PORT%/dev-ui/
.venv\Scripts\python.exe -m google.adk.cli web agents --port %PORT% --host 127.0.0.1
pause
