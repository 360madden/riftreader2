@echo off
setlocal
set "legacy=%~dp0artifacts\movement-upgrade\legacy-a4711ed\source"
if not exist "%legacy%\scripts\launch_physical_waypoints.py" (
  echo The preserved local movement helper is missing.
  echo See docs\planning\movement-helper-upgrade-2026-11-14.md for the baseline.
  exit /b 2
)
cd /d "%legacy%"
start "" /b pythonw "%legacy%\scripts\launch_physical_waypoints.py" %*
