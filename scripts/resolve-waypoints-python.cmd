@echo off
rem The caller uses SETLOCAL so interpreter selection stays private to the launcher.
set "_rr2_waypoints_python="
set "_rr2_waypoints_python_args="
if defined RIFTREADER2_PYTHON goto override

for %%D in ("%~dp0..\.local\physical-python-link" "%~dp0..\.local\physical-python") do (
  if exist "%%~D\.ready" if exist "%%~D\core\Scripts\python.exe" (
    set "_rr2_waypoints_python=%%~D\core\Scripts\python.exe"
    call :probe
    if not errorlevel 1 exit /b 0
  )
)
if exist "%~dp0..\.venv\Scripts\python.exe" (
  set "_rr2_waypoints_python=%~dp0..\.venv\Scripts\python.exe"
  call :probe
  if not errorlevel 1 exit /b 0
)

rem A WindowsApps python.exe alias alone can launch the Store instead of Python.
for /f "delims=" %%P in ('"%SystemRoot%\System32\where.exe" $PATH:python.exe 2^>nul') do (
  if /i not "%%P"=="%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe" if /i not "%%P"=="%USERPROFILE%\AppData\Local\Microsoft\WindowsApps\python.exe" (
    set "_rr2_waypoints_python=%%P"
    call :probe
    if not errorlevel 1 exit /b 0
  )
)

for /f "delims=" %%P in ('"%SystemRoot%\System32\where.exe" $PATH:py.exe 2^>nul') do (
  set "_rr2_waypoints_python=%%P"
  set "_rr2_waypoints_python_args=-3"
  call :probe
  if not errorlevel 1 exit /b 0
)

>&2 echo A working Python was not found. Install Python with Tcl/Tk or set RIFTREADER2_PYTHON to python.exe.
exit /b 2

:override
if not exist "%RIFTREADER2_PYTHON%" (
  >&2 echo RIFTREADER2_PYTHON does not point to an existing Python executable.
  exit /b 2
)
for %%P in ("%RIFTREADER2_PYTHON%") do set "_rr2_waypoints_python=%%~fP"
exit /b 0

:probe
rem A copied virtual environment can have an executable with a missing base installation.
"%_rr2_waypoints_python%" %_rr2_waypoints_python_args% -I -S -B -c "pass" >nul 2>nul && exit /b 0
exit /b 1
