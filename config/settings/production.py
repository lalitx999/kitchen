"""
ค่าสำหรับ server จริง
Caddy อยู่หน้าสุด: ทำ HTTPS และเสิร์ฟ /static/ กับ /media/ เอง Django ไม่ต้องเสิร์ฟไฟล์

ขั้นที่ 1 (ยังไม่มีโดเมน เปิดด้วย IP ผ่าน HTTP): ตั้ง HTTPS_ENABLED=False
ขั้นที่ 2 (ชี้โดเมนแล้ว Caddy ออกใบรับรองให้): ตั้ง HTTPS_ENABLED=True
"""
from .base import *  # noqa: F403
from .base import env

DEBUG = False
# + localhost สำหรับ healthcheck ภายในคอนเทนเนอร์ (Docker ตรวจว่าเว็บยังทำงาน)
ALLOWED_HOSTS = [*env.list('DJANGO_ALLOWED_HOSTS', default=['tmth-th.com', 'www.tmth-th.com']), 'localhost']
CSRF_TRUSTED_ORIGINS = env.list(
    'CSRF_TRUSTED_ORIGINS', default=['https://tmth-th.com', 'https://www.tmth-th.com']
)

# Caddy ส่ง X-Forwarded-Proto มา ให้ Django รู้ว่า request จริงเป็น HTTPS หรือไม่
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# ถ้าเปิด Secure cookie ตอนยังเป็น HTTP เบราว์เซอร์จะไม่เก็บ cookie = ล็อกอินไม่ได้ จึงผูกกับสวิตช์เดียว
HTTPS_ENABLED = env.bool('HTTPS_ENABLED', default=True)
SECURE_SSL_REDIRECT = HTTPS_ENABLED
SESSION_COOKIE_SECURE = HTTPS_ENABLED
CSRF_COOKIE_SECURE = HTTPS_ENABLED
# HSTS: เบราว์เซอร์จำว่าต้องใช้ HTTPS เสมอ · เปิดเฉพาะเมื่อ HTTPS ใช้ได้จริงแล้ว
SECURE_HSTS_SECONDS = env.int('SECURE_HSTS_SECONDS', default=60 * 60 * 24 * 30) if HTTPS_ENABLED else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False  # api.tmth-th.com ของระบบเดิมยังอยู่ ค่อยเปิดหลังปิดระบบเดิม
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
X_FRAME_OPTIONS = 'DENY'

# ชื่อไฟล์ static มี hash ต่อท้าย ทำให้ Caddy cache ได้นานโดยไม่ค้างของเก่า
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.ManifestStaticFilesStorage'},
}

EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
