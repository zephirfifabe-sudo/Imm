@echo off
REM ============================================================================
REM  CREER_EXE.bat - Construit dist\MalleTranscriber.exe en un double-clic
REM  1) trouve Python  2) crée un environnement isolé .venv  3) installe les
REM  dépendances  4) récupère ffmpeg.exe  5) lance PyInstaller --onefile
REM ============================================================================
chcp 65001 >nul
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title Construction de MalleTranscriber.exe

echo.
echo  ==========================================================
echo     MalleTranscriber - construction de l'executable
echo  ==========================================================
echo.

REM ---------------------------------------------------------------------------
REM 1. Recherche de Python (lanceur "py" d'abord, puis "python")
REM    Attention : "python" peut être le faux raccourci du Microsoft Store,
REM    on vérifie donc qu'il s'exécute vraiment.
REM ---------------------------------------------------------------------------
set "PY="
for %%V in (3.12 3.11 3.10 3.13) do (
    if not defined PY (
        py -%%V -c "import sys" >nul 2>&1 && set "PY=py -%%V"
    )
)
if not defined PY (
    python -c "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
    echo  [ERREUR] Python est introuvable sur ce PC.
    echo.
    echo  Installez Python 3.12 depuis https://www.python.org/downloads/windows/
    echo  IMPORTANT : cochez la case "Add python.exe to PATH" au debut de l'installation.
    echo  Puis relancez CREER_EXE.bat.
    echo.
    pause
    exit /b 1
)
for /f "tokens=2" %%I in ('%PY% --version 2^>^&1') do set "PYVER=%%I"
echo  [OK] Python %PYVER% trouve  (%PY%)

REM ---------------------------------------------------------------------------
REM 2. Environnement virtuel isolé (évite d'embarquer d'autres paquets du PC
REM    dans l'exe, ce qui le rendrait énorme)
REM ---------------------------------------------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo  [..] Creation de l'environnement .venv ...
    %PY% -m venv .venv
    if errorlevel 1 (
        echo  [ERREUR] Impossible de creer l'environnement virtuel.
        pause
        exit /b 1
    )
)
set "VPY=%CD%\.venv\Scripts\python.exe"

echo  [..] Installation des dependances (quelques minutes la premiere fois) ...
"%VPY%" -m pip install --upgrade pip --disable-pip-version-check -q
"%VPY%" -m pip install -r requirements.txt --disable-pip-version-check
if errorlevel 1 (
    echo.
    echo  [ERREUR] L'installation des dependances a echoue.
    echo  Verifiez votre connexion Internet. Si l'erreur parle de "Microsoft Visual C++",
    echo  installez https://aka.ms/vs/17/release/vc_redist.x64.exe puis relancez.
    pause
    exit /b 1
)
echo  [OK] Dependances installees

REM Vérification que le moteur se charge (détecte un VCRedist manquant)
"%VPY%" -c "import ctranslate2, faster_whisper" >nul 2>&1
if errorlevel 1 (
    echo.
    echo  [ERREUR] Le moteur CTranslate2 ne se charge pas.
    echo  Installez Microsoft Visual C++ Redistributable :
    echo     https://aka.ms/vs/17/release/vc_redist.x64.exe
    echo  puis relancez CREER_EXE.bat.
    pause
    exit /b 1
)

REM ---------------------------------------------------------------------------
REM 3. ffmpeg.exe : dossier ffmpeg\, sinon ffmpeg du PATH (winget), sinon téléchargement
REM ---------------------------------------------------------------------------
if not exist "ffmpeg" mkdir "ffmpeg"
if exist "ffmpeg\ffmpeg.exe" goto ffmpeg_ok

set "FFSRC="
for /f "delims=" %%F in ('where ffmpeg 2^>nul') do if not defined FFSRC set "FFSRC=%%F"
if defined FFSRC (
    echo  [..] ffmpeg trouve dans le PATH : !FFSRC!
    copy /y "!FFSRC!" "ffmpeg\ffmpeg.exe" >nul
    if exist "ffmpeg\ffmpeg.exe" goto ffmpeg_ok
)

echo  [..] Telechargement de ffmpeg (gyan.dev, ~100 Mo) ...
set "FFZIP=%TEMP%\malle_ffmpeg.zip"
set "FFDIR=%TEMP%\malle_ffmpeg"
curl -L --fail --retry 3 -o "%FFZIP%" "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
if errorlevel 1 goto ffmpeg_absent
if exist "%FFDIR%" rmdir /s /q "%FFDIR%"
mkdir "%FFDIR%"
tar -xf "%FFZIP%" -C "%FFDIR%"
for /r "%FFDIR%" %%F in (ffmpeg.exe) do if exist "%%F" copy /y "%%F" "ffmpeg\ffmpeg.exe" >nul
del /q "%FFZIP%" >nul 2>&1
rmdir /s /q "%FFDIR%" >nul 2>&1
if exist "ffmpeg\ffmpeg.exe" goto ffmpeg_ok

:ffmpeg_absent
echo  [ATTENTION] ffmpeg n'a pas pu etre recupere.
echo              L'exe utilisera le decodeur integre (PyAV) : la plupart des fichiers marchent.
echo              Pour l'inclure : "winget install Gyan.FFmpeg" puis relancez ce script,
echo              ou copiez ffmpeg.exe dans le dossier ffmpeg\ a cote de ce script.
set "ADDBIN="
goto build

:ffmpeg_ok
echo  [OK] ffmpeg.exe sera embarque dans l'executable
set "ADDBIN=--add-binary ffmpeg\ffmpeg.exe;."

REM ---------------------------------------------------------------------------
REM 4. PyInstaller
REM ---------------------------------------------------------------------------
:build
echo  [..] Construction de l'exe (3 a 6 minutes) ...
if exist "build" rmdir /s /q "build"
if exist "dist\MalleTranscriber.exe" del /q "dist\MalleTranscriber.exe"

"%VPY%" -m PyInstaller --noconfirm --clean --onefile --windowed ^
    --name MalleTranscriber ^
    %ADDBIN% ^
    --collect-all customtkinter ^
    --collect-all tkinterdnd2 ^
    --collect-all faster_whisper ^
    --collect-all ctranslate2 ^
    --collect-binaries onnxruntime ^
    --collect-binaries av ^
    --hidden-import av ^
    --hidden-import tokenizers ^
    --exclude-module torch ^
    --exclude-module tensorflow ^
    --exclude-module matplotlib ^
    --exclude-module scipy ^
    --exclude-module pandas ^
    --exclude-module IPython ^
    --exclude-module PyQt5 ^
    --exclude-module PySide6 ^
    src\main.py

if not exist "dist\MalleTranscriber.exe" (
    echo.
    echo  [ERREUR] La construction a echoue. Lisez les messages ci-dessus.
    pause
    exit /b 1
)

for %%A in ("dist\MalleTranscriber.exe") do set "TAILLE=%%~zA"
set /a TAILLE_MO=%TAILLE:~0,-6%+0
echo.
echo  ==========================================================
echo   TERMINE !  dist\MalleTranscriber.exe  (~%TAILLE_MO% Mo)
echo  ==========================================================
echo   Les modeles Whisper ne sont PAS dans l'exe : ils se telechargent
echo   une seule fois au premier usage dans %%USERPROFILE%%\.cache\huggingface
echo.
explorer "dist"
pause
