import os
from dotenv import load_dotenv

load_dotenv()

# Gunicorn 只需要这个文件存在
from app_server import app  # noqa