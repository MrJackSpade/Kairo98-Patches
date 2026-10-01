@echo off
setlocal DisableDelayedExpansion

set "launcher_dir=%~dp0"
set "drop_count=0"
if "%~1"=="" goto usage

:collect
if "%~1"=="" goto run
set /a drop_count+=1 >nul
set "CLEAR_DROP_%drop_count%=%~f1"
shift /1
goto collect

:run
set "CLEAR_DROP_COUNT=%drop_count%"
set "python=%launcher_dir%translation-pipeline\runtime\python\python.exe"
if not exist "%python%" goto missing_python
"%python%" "%launcher_dir%translation-pipeline\clear_english.py" --batch-from-env
set "clear_exit=%ERRORLEVEL%"
goto done

:usage
echo Drag a script file or folder onto this batch file to clear its English.
echo Folders are scanned recursively for strings.json.
set "clear_exit=1"
goto done

:missing_python
echo Python is missing: "%python%"
set "clear_exit=1"
goto done

:done
echo.
pause
exit /b %clear_exit%
