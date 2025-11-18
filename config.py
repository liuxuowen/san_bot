"""
Configuration settings for the WeChat Work Bot
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration"""
    # Flask settings
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    
    # WeChat Work settings
    WECHAT_CORP_ID = os.environ.get('WECHAT_CORP_ID', '')
    WECHAT_CORP_SECRET = os.environ.get('WECHAT_CORP_SECRET', '')
    WECHAT_AGENT_ID = os.environ.get('WECHAT_AGENT_ID', '')
    WECHAT_TOKEN = os.environ.get('WECHAT_TOKEN', '')
    WECHAT_ENCODING_AES_KEY = os.environ.get('WECHAT_ENCODING_AES_KEY', '')

    # WeChat Service Account settings
    FUWUHAO_APP_ID = os.environ.get('FUWUHAO_APP_ID', '')
    FUWUHAO_APP_SECRET = os.environ.get('FUWUHAO_APP_SECRET', '')
    FUWUHAO_TOKEN = os.environ.get('FUWUHAO_TOKEN', '')
    FUWUHAO_ENCODING_AES_KEY = os.environ.get('FUWUHAO_ENCODING_AES_KEY', '')
    
    # File upload settings
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    ALLOWED_EXTENSIONS = {'txt', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'csv', 'json'}
    HIGH_DELTA_THRESHOLD = int(os.environ.get('HIGH_DELTA_THRESHOLD', '5000'))
    PUBLIC_BASE_URL = os.environ.get('PUBLIC_BASE_URL', '').rstrip('/')
    ACCESS_LOG_LEVEL = os.environ.get('ACCESS_LOG_LEVEL', 'ERROR')  # e.g. ERROR/WARNING/INFO/NONE
    # Database settings
    MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
    MYSQL_PORT = int(os.environ.get('MYSQL_PORT', '3306'))
    MYSQL_USER = os.environ.get('MYSQL_USER', '')
    MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
    MYSQL_DB = os.environ.get('MYSQL_DB', 'sanzhan')
    
    # Application settings
    DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'
    HOST = os.environ.get('HOST', '0.0.0.0')
    PORT = int(os.environ.get('PORT', 5000))


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
