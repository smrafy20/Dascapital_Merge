"""WSGI entrypoint for this Flask app.
Use with gunicorn/waitress/etc.: module:app
"""

from main import app

if __name__ == "__main__":
    # Dev run fallback
    app.run(debug=True, port=1158)
