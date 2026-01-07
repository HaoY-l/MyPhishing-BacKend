#!/bin/bash
set -e

# 🔍 检测运行环境
if [ -f /.dockerenv ] || grep -q docker /proc/1/cgroup 2>/dev/null; then
    echo "🐳 检测到 Docker 容器环境"
    IN_DOCKER=true
    PYTHON=python
    GUNICORN=gunicorn
    CELERY=celery
else
    echo "🖥️  检测到宿主机环境"
    IN_DOCKER=false
    VENV=./venv/bin
    PYTHON=$VENV/python3.11
    GUNICORN=$VENV/gunicorn
    CELERY=$VENV/celery
fi

# 🧹 宿主机需要清理端口
if [ "$IN_DOCKER" = false ]; then
    echo "🧹 清理端口..."
    fuser -k 8000/tcp >/dev/null 2>&1 || true
    fuser -k 25/tcp   >/dev/null 2>&1 || true
    
    pkill -9 -f celery || true
    pkill -9 -f gunicorn || true
    pkill -9 -f smtp_server.py || true
    
    sleep 2
fi

echo "🚀 执行系统初始化..."
$PYTHON db_server.py || exit 1

echo "🚀 启动 Celery..."
if [ "$IN_DOCKER" = true ]; then
    # 容器内后台运行
    $CELERY -A celery_server.celery_app worker \
        --loglevel=info \
        --concurrency=2 &
else
    # 宿主机用 nohup
    nohup $CELERY -A celery_server.celery_app worker \
        --loglevel=info \
        --concurrency=2 \
        > celery.log 2>&1 &
fi

echo "🚀 启动 SMTP..."
if [ "$IN_DOCKER" = true ]; then
    $PYTHON smtp_server.py &
else
    nohup $PYTHON smtp_server.py > gateway.log 2>&1 &
fi

echo "🚀 启动 API (Gunicorn)..."
if [ "$IN_DOCKER" = true ]; then
    # 容器内前台运行（重要！）
    exec $GUNICORN -w 1 --threads 4 -k gthread \
        -b 0.0.0.0:8000 \
        --access-logfile - \
        --error-logfile - \
        api_server:app
else
    # 宿主机后台运行
    nohup $GUNICORN -w 1 --threads 4 -k gthread \
        -b 0.0.0.0:8000 \
        api_server:app \
        > flask.log 2>&1 &
    
    echo "✅ 所有服务已启动"
    echo "📜 日志：tail -f celery.log flask.log gateway.log"
fi
