@echo off
set "PATH=C:\Users\sus\AppData\Local\Programs\Python\Python313;C:\Users\sus\AppData\Local\Programs\Python\Python313\Scripts;%PATH%"
echo ========================================================
echo  Starting LeadMaps BI Server (Neo Brutalism Edition)
echo  Buka di Browser: http://localhost:8000
echo ========================================================
python -m uvicorn app.main:app --reload --port 8000
