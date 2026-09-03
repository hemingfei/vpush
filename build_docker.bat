@echo off
setlocal
cd /d "%~dp0"

echo [1/3] Building vpush:latest ...
docker build --build-arg PIP_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple -t vpush:latest .
if errorlevel 1 goto :fail

echo [2/3] Building vpush-waf-bot:latest ...
docker build -t vpush-waf-bot:latest .\waf-bot
if errorlevel 1 goto :fail

echo [3/3] Saving images to vpush-latest.tar ...
docker save vpush:latest vpush-waf-bot:latest -o vpush-latest.tar
if errorlevel 1 goto :fail

echo [DONE] Output: %CD%\vpush-latest.tar
dir vpush-latest.tar | findstr vpush-latest
exit /b 0

:fail
echo [ERROR] Build failed.
exit /b 1
