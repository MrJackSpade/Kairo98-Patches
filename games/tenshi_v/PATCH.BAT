@echo off
rem Standard patch runner: identical in every games\<title>\ folder.
rem Double-click to patch the collection copy of this game, or drop a disk
rem image onto this file.  The result is written to the output\ folder here.
setlocal
cd /d "%~dp0"
where python >nul 2>nul || (echo Python 3 is required: https://www.python.org/ & set RC=1 & goto end)
python "%~dp0..\..\tools\run_patch.py" "%~dp0." %1
set RC=%errorlevel%
:end
if not defined NOPAUSE pause
exit /b %RC%
