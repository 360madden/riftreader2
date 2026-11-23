@echo off
setlocal DisableDelayedExpansion
call "%~dp0scripts\resolve-waypoints-python.cmd"
if errorlevel 1 exit /b %errorlevel%
if not defined RIFTREADER2_PYTHON (
  "%_rr2_waypoints_python%" %_rr2_waypoints_python_args% -I -S -B -c "pass" >nul 2>nul
  if errorlevel 1 (
    call "%~dp0scripts\resolve-waypoints-python.cmd" --prefer-system
    if errorlevel 1 exit /b 2
  )
)
"%_rr2_waypoints_python%" %_rr2_waypoints_python_args% -B "%~dp0scripts\setup_physical_python.py" %*
exit /b %errorlevel%
