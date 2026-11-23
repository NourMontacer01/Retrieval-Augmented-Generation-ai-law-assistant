@echo off
rem Regenere docs\rapport.pdf a partir de rapport.html, avec Microsoft Edge (installe sur Windows).
cd /d "%~dp0"
"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --headless=new --disable-gpu --no-pdf-header-footer --virtual-time-budget=15000 --print-to-pdf="%~dp0..\rapport.pdf" "%~dp0rapport.html"
echo PDF regenere : docs\rapport.pdf
