@echo off
rem The caller uses SETLOCAL so interpreter selection stays private to the launcher.
set "_rr2_waypoints_python="
set "_rr2_waypoints_python_args="
if defined RIFTREADER2_PYTHON goto override
if /i "%~1"=="--prefer-system" goto system

:checkout
for %%D in ("%~dp0..\.local\physical-python-link" "%~dp0..\.local\physical-python") do (
  if exist "%%~D\.ready" if exist "%%~D\core\Scripts\python.exe" (
    set "_rr2_waypoints_python=%%~D\core\Scripts\python.exe"
    exit /b 0
  )
)
if exist "%~dp0..\.venv\Scripts\python.exe" (
  set "_rr2_waypoints_python=%~dp0..\.venv\Scripts\python.exe"
  exit /b 0
)
if /i "%~1"=="--prefer-system" goto unavailable

:system
rem A WindowsApps python.exe alias alone can launch the Store instead of Python.
for /f "delims=" %%P in ('"%SystemRoot%\System32\where.exe" $PATH:python.exe 2^>nul') do (
  if /i not "%%P"=="%LOCALAPPDATA%\Microsoft\WindowsApps\python.exe" if /i not "%%P"=="%USERPROFILE%\AppData\Local\Microsoft\WindowsApps\python.exe" (
    set "_rr2_waypoints_python=%%P"
    exit /b 0
  )
)

for %%P in (py.exe) do set "_rr2_waypoints_python=%%~$PATH:P"
if defined _rr2_waypoints_python (
  set "_rr2_waypoints_python_args=-3"
  exit /b 0
)
if /i "%~1"=="--prefer-system" goto checkout

:unavailable
>&2 echo Python was not found. Install Python with Tcl/Tk or set RIFTREADER2_PYTHON to python.exe.
exit /b 2

:override
if not exist "%RIFTREADER2_PYTHON%" (
  >&2 echo RIFTREADER2_PYTHON does not point to an existing Python executable.
  exit /b 2
)
for %%P in ("%RIFTREADER2_PYTHON%") do set "_rr2_waypoints_python=%%~fP"
exit /b 0
