"""ค่าสำหรับพัฒนาบนเครื่องตัวเอง"""
from .base import *  # noqa: F403
from .base import env

DEBUG = True
ALLOWED_HOSTS = env.list('DJANGO_ALLOWED_HOSTS', default=['localhost', '127.0.0.1'])

# ระหว่างพัฒนาเปิด Django Admin ไว้ดูข้อมูลได้
DJANGO_ADMIN_ENABLED = env.bool('DJANGO_ADMIN_ENABLED', default=True)

EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# ---- รันบนเครื่องโดยไม่ใช้ Docker ----
# ฐานข้อมูลทดสอบสร้างจาก template ที่มี PostGIS อยู่แล้ว (role ของแอปไม่ต้องเป็น superuser)
DB_TEST_TEMPLATE = env('DB_TEST_TEMPLATE', default='')
if DB_TEST_TEMPLATE:
    DATABASES['default']['TEST'] = {'TEMPLATE': DB_TEST_TEMPLATE}  # noqa: F405

# ไม่มี Redis บนเครื่อง (REDIS_URL ว่าง) -> cache ในหน่วยความจำ + Celery รันงานทันทีใน process เดียว
# ใช้ได้แค่ตอนพัฒนา: พิกัดไรเดอร์ใน cache จะไม่แชร์ข้าม process และหายเมื่อรีสตาร์ต
if not env('REDIS_URL', default=''):
    CACHES = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache', 'LOCATION': 'tmpp'}}
    SESSION_ENGINE = 'django.contrib.sessions.backends.db'
    CELERY_TASK_ALWAYS_EAGER = True
    CELERY_TASK_EAGER_PROPAGATES = True
    CELERY_BROKER_URL = 'memory://'
    CELERY_RESULT_BACKEND = 'cache+memory://'

# บน Mac ที่ลง GDAL ผ่าน Homebrew บางเครื่องต้องบอก path เอง (ใส่ใน .env ถ้า check แล้ว error)
GDAL_LIBRARY_PATH = env('GDAL_LIBRARY_PATH', default=None)
GEOS_LIBRARY_PATH = env('GEOS_LIBRARY_PATH', default=None)
