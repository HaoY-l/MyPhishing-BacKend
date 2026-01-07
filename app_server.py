import os, sys
from flask import Flask
from flask_cors import CORS

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.api import api_bp
# 导入授权模块
from src.api.utils import license_bp, register_license_middleware

def create_app():
    app = Flask(__name__)
    
    # 注册所有蓝图
    app.register_blueprint(api_bp)
    app.register_blueprint(license_bp)  # 注册授权蓝图
    
    CORS(app)
    
    # 注册授权中间件（必须在蓝图注册之后）
    register_license_middleware(app)
    
    return app

# ⚠️ Gunicorn 通过 app:app 加载
app = create_app()