@echo off
title Backend FastAPI - Hackathon UTA 2026
cd /d "C:\Users\Acer Predator\Documents\Quinto\Hack"
set PYTHONPATH=backend\src
echo =======================================================
echo   Iniciando Backend FastAPI (REST, WebSockets, Supabase)
echo =======================================================
echo   API URL: http://localhost:8000
echo   Docs:    http://localhost:8000/docs
echo =======================================================
echo.
"C:\Users\Acer Predator\Documents\Quinto\.venv\Scripts\python.exe" -m uvicorn main:app --app-dir backend/src --host 0.0.0.0 --port 8000 --reload
pause
