@echo off
title NCLPDLB - Pokemon Draft League Bot
cd /d "%~dp0"
echo Starting Pokemon Draft League Bot...
echo.
.venv\Scripts\python src\bot\main.py
echo.
echo Bot exited with code %ERRORLEVEL%.
pause
