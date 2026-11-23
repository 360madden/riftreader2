@echo off
setlocal DisableDelayedExpansion
call "%~dp0scripts\resolve-waypoints-python.cmd"
if errorlevel 1 exit /b %errorlevel%
pushd "%~dp0" || exit /b 2
"%_rr2_waypoints_python%" %_rr2_waypoints_python_args% "%~dp0scripts\launch_physical_waypoints.py" --detach-window %*
set "_rr2_waypoints_exit=%errorlevel%"
popd
exit /b %_rr2_waypoints_exit%
