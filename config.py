import os
import secrets
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Generate a random secret key if one doesn't exist
    SECRET_KEY = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
    WTF_CSRF_ENABLED = True
    WTF_CSRF_SECRET_KEY = os.getenv('WTF_CSRF_SECRET_KEY', 'csrf-key-for-testing-only')
    
    # Database configuration
    basedir = os.path.abspath(os.path.dirname(__file__))
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + os.path.join(basedir, 'instance', 'odnoklassniki.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Upload folder for lead files
    UPLOAD_FOLDER = os.path.join(basedir, 'uploads')
    
    # Ensure instance folder exists
    os.makedirs(os.path.join(basedir, 'instance'), exist_ok=True)
    
    # Messaging delays (in seconds)
    MIN_DELAY = 15
    MAX_DELAY = 30
    
    # Proxy timeout in seconds
    PROXY_TIMEOUT = 10
    
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size 