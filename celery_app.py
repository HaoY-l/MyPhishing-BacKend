# celery_app.py
from celery import Celery
import os

# 统一 Celery 实例
celery_app = Celery(
    'mail_tasks',
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0")
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Shanghai',
    enable_utc=True,
    worker_prefetch_multiplier=1  # 防止任务堆积
)