@echo off
rem Recueil de conformite - lancement en un double-clic.
rem Premiere fois : installe l'environnement Python et construit la base (40 min environ).
rem Fois suivantes : ouvre directement l'interface.

setlocal
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
set PY=.venv\Scripts\python.exe

echo.
echo  Recueil de conformite
echo  ---------------------

rem 1. Environnement Python
if not exist "%PY%" (
    echo  Creation de l'environnement Python...
    python -m venv .venv || goto :erreur_python
    "%PY%" -m pip install --upgrade pip >nul
    echo  Installation des bibliotheques ^(quelques minutes^)...
    "%PY%" -m pip install -r requirements.txt || goto :erreur
)

rem 2. Choix
if "%~1"=="" (
    echo.
    echo   1. Ouvrir l'interface              ^(par defaut^)
    echo   2. Reconstruire la base             ^(telechargement, decoupage, indexation^)
    echo   3. Mesurer la qualite de la recherche
    echo.
    set /p CHOIX=" Votre choix [1] : "
) else (
    set CHOIX=%~1
)
if "%CHOIX%"=="" set CHOIX=1

if "%CHOIX%"=="2" goto :construire
if "%CHOIX%"=="3" goto :evaluer

rem 3. Interface : la base doit exister
if not exist "db\chroma" (
    echo  Base absente : construction avant le premier lancement.
    call :etapes || goto :erreur
)
echo  Demarrage du serveur, le navigateur s'ouvrira tout seul...
"%PY%" -m conformite.app --ouvrir
goto :fin

:construire
call :etapes || goto :erreur
goto :fin

:evaluer
if exist "tests\questions\questions.json" (
    "%PY%" -m conformite.evaluation
) else (
    echo  tests\questions\questions.json absent : evaluation sur le jeu de mise au point.
    "%PY%" -m conformite.evaluation --fichier tests\questions\questions_mise_au_point.json --ablation
)
pause
goto :fin

:etapes
echo  [1/3] Telechargement des textes...
"%PY%" -m conformite.collecte || exit /b 1
echo  [2/3] Decoupage en articles...
"%PY%" -m conformite.decoupage || exit /b 1
echo  [3/3] Indexation ^(longue la premiere fois^)...
"%PY%" -m conformite.index || exit /b 1
exit /b 0

:erreur_python
echo  Python introuvable. Installer Python 3.11 ou plus recent depuis python.org,
echo  en cochant "Add python.exe to PATH", puis relancer ce fichier.
pause
exit /b 1

:erreur
echo  Une etape a echoue : voir le message ci-dessus.
pause
exit /b 1

:fin
endlocal
