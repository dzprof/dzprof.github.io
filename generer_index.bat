@echo off
cd /d "%~dp0"
echo ============================================================
echo   Generation des index (dossier journaux_index et fichier .json)
echo ============================================================
echo.

where py >nul 2>nul
if %errorlevel%==0 (
  set "PY=py -3"
) else (
  where python >nul 2>nul
  if %errorlevel%==0 (
    set "PY=python"
  ) else (
    echo ERREUR : Python n'est pas installe ou n'est pas dans le PATH.
    echo Solution sans Python : ouvrez generer_index_sans_python.html
    echo puis selectionnez le dossier JOURNAUX.
    pause
    exit /b 1
  )
)

%PY% --version
%PY% -c "import fitz" >nul 2>nul
if errorlevel 1 (
  echo Installation de PyMuPDF...
  %PY% -m pip install PyMuPDF
  if errorlevel 1 (
    echo ERREUR : impossible d'installer PyMuPDF.
    echo Solution sans Python : ouvrez generer_index_sans_python.html
    pause
    exit /b 1
  )
)

%PY% generer_index.py
if errorlevel 1 (
  echo.
  echo ERREUR pendant la generation.
  pause
  exit /b 1
)

echo.
echo OK : journaux_index/ (fichiers par annee + predateurs) et journaux_index.json sont prets.
pause
