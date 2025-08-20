import os
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()

# Secrets and database
SECRET_KEY = os.getenv('SECRET_KEY', 'your-secret-key')
SQLALCHEMY_DATABASE_URI = os.getenv('SQLALCHEMY_DATABASE_URI', 'mysql+mysqlconnector://root:1234@localhost/saif')
SQLALCHEMY_TRACK_MODIFICATIONS = os.getenv('SQLALCHEMY_TRACK_MODIFICATIONS', 'False').lower() in ('1','true','yes')

# AI / Search keys (referenced elsewhere)
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')
GEMINI_MODEL = os.getenv('GEMINI_MODEL', 'gemini-2.0-flash')
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY', '')
GOOGLE_CSE_ID = os.getenv('GOOGLE_CSE_ID', '')


class Config:
	SECRET_KEY = SECRET_KEY
	SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI
	SQLALCHEMY_TRACK_MODIFICATIONS = SQLALCHEMY_TRACK_MODIFICATIONS
