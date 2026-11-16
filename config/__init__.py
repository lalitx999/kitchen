# โหลด Celery app ตอน Django เริ่ม เพื่อให้ @shared_task ผูกกับ app นี้
from .celery import app as celery_app

__all__ = ('celery_app',)
