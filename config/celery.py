import os

from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')

app = Celery('tmpp')
# อ่านค่าที่ขึ้นต้นด้วย CELERY_ จาก Django settings
app.config_from_object('django.conf:settings', namespace='CELERY')
# ค้นหา tasks.py ในทุก app อัตโนมัติ
app.autodiscover_tasks()
