@echo off
echo ========================================================
echo Updating Teamzen Server
echo ========================================================
cd /d c:\teamzen-server\Teamzen-Server

:: 1. Pull latest code changes
echo [1/3] Pulling latest code changes...
git pull
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] git pull failed. Please check for local merge conflicts.
    exit /b %ERRORLEVEL%
)

:: 2. Apply database migrations
echo [2/3] Applying database migrations...
call venv\Scripts\activate
call python manage.py migrate
if %ERRORLEVEL% NEQ 0 (
    echo [WARNING] Migration failed or encountered an issue. Continuing...
)

:: 3. Restart services
echo [3/3] Restarting server services...
:: Stop existing Django, Celery Worker, and Celery Beat windows
:: Note: Do NOT kill Auto Updater or this updater window!
taskkill /FI "WINDOWTITLE eq Django Server*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Celery Worker*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Celery Beat*" /T /F >nul 2>&1

:: Wait 2 seconds for processes to cleanly release ports
timeout /t 2 /nobreak >nul

:: Launch refreshed service windows
start "Django Server" cmd /k "cd /d c:\teamzen-server\Teamzen-Server && call venv\Scripts\activate && python manage.py runserver"
start "Celery Worker" cmd /k "cd /d c:\teamzen-server\Teamzen-Server && call venv\Scripts\activate && call run_celery.bat"
start "Celery Beat" cmd /k "cd /d c:\teamzen-server\Teamzen-Server && call venv\Scripts\activate && celery -A config beat -l info"

echo ========================================================
echo All services have been successfully updated and restarted!
echo ========================================================
