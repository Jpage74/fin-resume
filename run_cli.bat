@echo off
rem 求职助手 CLI 启动脚本（Windows）
rem 用法: run_cli.bat --file jd.txt     或   run_cli.bat "JD文本"
cd /d %~dp0
set PYTHONPATH=src
.venv\Scripts\python.exe -m job_assistant.cli %*
