@echo off
rem Job Assistant CLI launcher (Windows)
rem Usage: run_cli.bat --file jd.txt   or   run_cli.bat "JD text"
cd /d %~dp0
set PYTHONPATH=src
.venv\Scripts\python.exe -m job_assistant.cli %*
