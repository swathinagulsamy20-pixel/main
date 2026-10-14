@echo off
title Smart Mini Project Management System
echo ===================================================
echo Starting Smart Mini Project Management System
echo Dept. of Information Technology
echo ===================================================
echo.

:: Initialize database if needed and start server
python -c "import database; database.init_db(); print('Database tables checked and verified.')"
echo Starting Flask application at http://localhost:5000 ...
python app.py
pause
