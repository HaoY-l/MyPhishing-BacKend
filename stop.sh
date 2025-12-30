#!/bin/bash

echo "🧹 清理端口..."
fuser -k 8000/tcp >/dev/null 2>&1
fuser -k 25/tcp   >/dev/null 2>&1

pkill -9 -f celery
pkill -9 -f gunicorn
pkill -9 -f smtp_server.py


echo "✅ 所有服务已停止"

