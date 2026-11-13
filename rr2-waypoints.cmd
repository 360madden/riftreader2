@echo off
python "%~dp0scripts\waypoints_cli.py" %*
exit /b %errorlevel%
