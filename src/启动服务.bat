@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "NODE_EXE=C:\Users\woshi\.workbuddy\binaries\node\versions\22.12.0\node.exe"
if exist "%NODE_EXE%" (
  "%NODE_EXE%" server.js
) else (
  node server.js
)
pause
