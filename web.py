"""Avvio del server web (sviluppo). In produzione usare un WSGI server (es. gunicorn 'web:create_app()')."""
import os

from sfm.env import env, env_bool
from web import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host=env("WEB_HOST") or "127.0.0.1", port=int(env("WEB_PORT") or 5000), debug=env_bool("FLASK_DEBUG", False))
