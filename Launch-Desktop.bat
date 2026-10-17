@echo off
setlocal
title AI Coding Desktop
set "PY=C:\ProgramData\anaconda3\python.exe"
if not exist "%PY%" set "PY=C:\ProgramData\xraylarch\python.exe"
cd /d "%~dp0sources\windows\app\bridge"
"%PY%" supervisor.py
if errorlevel 1 pause
endlocal
