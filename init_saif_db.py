"""
Initialize MySQL database 'saif' and create all tables from models.py using the main app.

Usage (PowerShell):
  python init_saif_db.py

Adjust MYSQL_USER/PASS/HOST if different from defaults.
"""

import mysql.connector
from mysql.connector import errorcode

# Adjust these if your MySQL credentials differ
MYSQL_HOST = 'localhost'
MYSQL_USER = 'root'
MYSQL_PASS = '1234'
DB_NAME = 'saif'


def create_database_if_needed():
    try:
        cnx = mysql.connector.connect(host=MYSQL_HOST, user=MYSQL_USER, password=MYSQL_PASS)
        cnx.autocommit = True
        cur = cnx.cursor()
        cur.execute(
            f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        cur.close()
        cnx.close()
        print(f"Database '{DB_NAME}' is ready.")
    except mysql.connector.Error as err:
        if err.errno == errorcode.ER_ACCESS_DENIED_ERROR:
            print("Access denied: Check your MySQL username/password in init_saif_db.py")
        else:
            print(f"Error creating database: {err}")
        raise


def create_tables():
    # Import after DB exists so SQLAlchemy can connect via main.py config
    from main import app, db  # uses mysql+mysqlconnector://root:1234@localhost/saif
    with app.app_context():
        db.create_all()
        print("All tables created (or already exist).")


if __name__ == '__main__':
    create_database_if_needed()
    create_tables()
