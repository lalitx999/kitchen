"""
ค่าสำหรับ server จริง (tmth-th.com)
Caddy อยู่หน้าสุด: ทำ HTTPS และเสิร์ฟ /static/ กับ /media/ เอง Django ไม่ต้องเสิร์ฟไฟล์
"""
from .base import *  # noqa: F403
from .base import env

DEBUG = False
ALLOWED_HOSTS = env.list('DJANGO_ALLOWED_HOSTS', default=['tmth-th.com', 'www.tmth-th.com'])
CSRF_TRUSTED_ORIGINS = env.list(
    'CSRF_TRUSTED_ORIGINS', default=['https://tmth-th.com', 'https://www.tmth-th.com']
)

# Caddy ส่ง X-Forwarded-Proto มา ให้ Django รู้ว่า request จริงเป็น HTTPS
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=True)
SECURE_HSTS_SECONDS = env.int('SECURE_HSTS_SECONDS', default=60 * 60 * 24 * 30)
SECURE_HSTS_INCLUDE_SUBDOMAINS = False  # api.tmth-th.com ของระบบเดิมยังอยู่ ค่อยเปิดหลังปิดระบบเดิม
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = 'DENY'

# ชื่อไฟล์ static มี hash ต่อท้าย ทำให้ Caddy cache ได้นานโดยไม่ค้างของเก่า
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'},
}

EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
