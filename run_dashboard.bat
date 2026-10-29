@echo off
title Dashboard Operador - Streamlit - Hackathon UTA 2026
cd /d "C:\Users\Acer Predator\Documents\Quinto\Hack"
set PYTHONPATH=dashboard
set API_BASE_URL=http://localhost:8000
set DASHBOARD_API_KEY=uta_secret_operator_key_2026

echo =======================================================
echo   Iniciando Dashboard Operador (Streamlit + Plotly)
echo =======================================================
echo   Dashboard URL: http://localhost:8501
echo =======================================================
echo.
"C:\Users\Acer Predator\Documents\Quinto\.venv\Scripts\python.exe" -m streamlit run dashboard/app.py
pause
