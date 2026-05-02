@echo off
setlocal
cd /d "%~dp0backend"

if exist .env (
  for /f "usebackq tokens=1,* delims==" %%A in (".env") do (
    if not "%%A"=="" if not "%%A:~0,1%"=="#" set "%%A=%%B"
  )
)

if "%APP_HOST%"=="" set APP_HOST=0.0.0.0
if "%APP_PORT%"=="" set APP_PORT=8080

python -m app.main
endlocal