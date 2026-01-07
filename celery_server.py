# celery_server.py
import os, sys
from dotenv import load_dotenv

load_dotenv()

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 导入 celery_app，保证 worker 能注册任务
from celery_app import celery_app
from src import tasks