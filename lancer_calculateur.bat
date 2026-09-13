@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  set "PY=py -3"
) else (
  set "PY=python"
)
start "" cmd /c "timeout /t 2 >nul & start http://localhost:8000/index.html"
%PY% -m http.server 8000
pause
