@echo off
echo Starting Teamzen Server Services...
cd /d c:\teamzen-server\Teamzen-Server

:: Start Django Server
start "Django Server" cmd /k "cd /d c:\teamzen-server\Teamzen-Server && call venv\Scripts\activate && python manage.py runserver"

:: Start Celery Worker
start "Celery Worker" cmd /k "cd /d c:\teamzen-server\Teamzen-Server && call venv\Scripts\activate && celery -A config worker -l info --pool=solo"

:: Start Celery Beat
start "Celery Beat" cmd /k "cd /d c:\teamzen-server\Teamzen-Server && call venv\Scripts\activate && celery -A config beat -l info"

:: Start Auto Updater
start "Auto Updater" cmd /k "cd /d c:\teamzen-server\Teamzen-Server && call venv\Scripts\activate && python auto_updater.py"
