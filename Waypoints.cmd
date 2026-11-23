@echo off
setlocal DisableDelayedExpansion
call "%~dp0scripts\resolve-waypoints-python.cmd"
if errorlevel 1 exit /b %errorlevel%
"%_rr2_waypoints_python%" %_rr2_waypoints_python_args% "%~dp0scripts\launch_physical_waypoints.py" --detach-window %*
exit /b %errorlevel%
