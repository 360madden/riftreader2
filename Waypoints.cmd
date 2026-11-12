@echo off
cd /d "%~dp0"
start "" /b pythonw "%~dp0scripts\launch_physical_waypoints.py" %*
