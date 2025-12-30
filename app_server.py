import os, sys
from flask import Flask
from flask_cors import CORS

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.api import api_bp

def create_app():
    app = Flask(__name__)
    app.register_blueprint(api_bp)
    CORS(app)
    return app

# ⚠️ Gunicorn 通过 app:app 加载
app = create_app()