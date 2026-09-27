@echo off
setlocal DisableDelayedExpansion

if "%~1"=="" goto usage
if not exist "%~f1" goto missing

echo Translating "%~f1"...
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0translation-pipeline\run-stream.ps1" -InputFile "%~f1"
set "translation_exit=%ERRORLEVEL%"
if not "%translation_exit%"=="0" echo Translation stopped with exit code %translation_exit%.
if "%translation_exit%"=="0" echo Translation finished.
goto done

:usage
echo Drag a script file onto this batch file to translate it.
set "translation_exit=1"
goto done

:missing
echo File not found: "%~f1"
set "translation_exit=1"

:done
echo.
pause
exit /b %translation_exit%
