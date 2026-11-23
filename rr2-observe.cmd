@echo off
setlocal DisableDelayedExpansion
call "%~dp0scripts\resolve-waypoints-python.cmd"
if errorlevel 1 exit /b %errorlevel%
"%_rr2_waypoints_python%" %_rr2_waypoints_python_args% -B "%~dp0scripts\observe_target.py" %*
exit /b %errorlevel%
