@echo off
echo Pulling latest code changes...
cd /d c:\teamzen-server\Teamzen-Server

:: Pull changes
git pull

echo Restarting services...
:: Kill existing windows based on Window Title
taskkill /FI "WINDOWTITLE eq Django Server*" /T /F
taskkill /FI "WINDOWTITLE eq Celery Worker*" /T /F
taskkill /FI "WINDOWTITLE eq Celery Beat*" /T /F
taskkill /FI "WINDOWTITLE eq Auto Updater*" /T /F

:: Relaunch everything
start "" "startup.bat"

:: Exit
exit
