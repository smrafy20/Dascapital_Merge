SECRET_KEY = 'your-secret-key'

# Centralized DB configuration used by main.py
# Adjust username/password/host/db as needed
SQLALCHEMY_DATABASE_URI = 'mysql+mysqlconnector://root:1234@localhost/saif'
SQLALCHEMY_TRACK_MODIFICATIONS = False


class Config:
	SECRET_KEY = SECRET_KEY
	SQLALCHEMY_DATABASE_URI = SQLALCHEMY_DATABASE_URI
	SQLALCHEMY_TRACK_MODIFICATIONS = SQLALCHEMY_TRACK_MODIFICATIONS
