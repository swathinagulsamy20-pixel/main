import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    BASE_DIR = BASE_DIR
    SECRET_KEY = os.environ.get('SECRET_KEY', 'smart-miniproject-secret-key-2025-2026')
    
    # MySQL Database Settings
    DB_HOST = os.environ.get('DB_HOST', 'localhost')
    DB_PORT = int(os.environ.get('DB_PORT', 3306))
    DB_USER = os.environ.get('DB_USER', 'root')
    DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
    DB_NAME = os.environ.get('DB_NAME', 'smart_miniproject_db')
    
    # Upload Directories
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    REPORTS_FOLDER = os.path.join(BASE_DIR, 'generated_reports')
    BACKUP_FOLDER = os.path.join(BASE_DIR, 'backups')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload
    ALLOWED_EXTENSIONS = {'xlsx', 'xls', 'sql'}
    
    # Application Defaults
    ACADEMIC_YEAR = '2025-2026'
    DEPARTMENT = 'Information Technology'
    DEFAULT_TEAM_PREFIX = '25ITP'
    DEFAULT_TEAM_STRENGTH = 3
    DEFAULT_PANEL_COUNT = 3
    DEFAULT_FACULTY_PER_PANEL = 3
