@echo off
title Pepetola Bot - CTT FISEI (Hackathon UTA 2026)
cd /d "C:\Users\Acer Predator\Documents\Quinto\Hack"
set PYTHONPATH=backend\src

echo =======================================================
echo   Iniciando Pepetola Bot (Telegram + LangGraph + Supabase)
echo =======================================================
echo   Bot Username: @pepetola_bot
echo   Para detener el bot presiona Ctrl + C
echo =======================================================
echo.

"C:\Users\Acer Predator\Documents\Quinto\.venv\Scripts\python.exe" -m modules.channels.runner

pause
