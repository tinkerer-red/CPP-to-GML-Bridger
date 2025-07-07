@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM File: build_bridge.bat
REM Description:  
REM   1) Initializes MSVC’s x64 tools environment  
REM   2) Runs the Python bridge generator (main.py)  
REM ─────────────────────────────────────────────────────────────────────────────

REM 1) Locate your VS “vcvarsall.bat” – adjust this path to your VS install if needed
set VS_VCVARS="C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat"

if not exist %VS_VCVARS% (
  echo ERROR: Could not find %VS_VCVARS%
  echo Please adjust the path in build_bridge.bat
  pause
  exit /b 1
)

REM 2) Call the VS dev environment for 64-bit
call %VS_VCVARS% x64

REM 3) Now run your Python script
REM    (Assumes 'py' launcher is on your PATH and your script is in the same folder)
py main.py %*

if ERRORLEVEL 1 (
  echo.
  echo Bridge generator failed with error %ERRORLEVEL%.
  pause
) else (
  echo.
  echo Bridge generation succeeded.
  pause
)
