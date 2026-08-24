@echo off
cd /d "%~dp0"
venv\Scripts\python.exe render_report.py >> output\monthly_report_log.txt 2>&1
