@echo off
cd /d "%~dp0"
python daemon.py --once
pause
