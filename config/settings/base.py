"""
ค่าที่ใช้ร่วมกันทุก environment
local.py และ production.py import จากไฟล์นี้แล้ว override เฉพาะที่ต่าง
ข้อมูลลับทั้งหมดอ่านจาก .env ผ่าน django-environ เท่านั้น
"""
from decimal import Decimal
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
# อ่าน .env ถ้ามี (บน server ใช้ env ของ container แทนได้)
environ.Env.read_env(BASE_DIR / '.env')

SECRET_KEY = env('DJANGO_SECRET_KEY')
DEBUG = False
ALLOWED_HOSTS: list[str] = []

# ---------------------------------------------------------------------------
# แบรนด์ / โดเมน
# ---------------------------------------------------------------------------
SITE_NAME = env('SITE_NAME', default='TMPP')
SITE_TAGLINE = env('SITE_TAGLINE', default='สั่งอาหารออนไลน์ ส่งถึงบ้าน')
SITE_URL = env('SITE_URL', default='http://localhost:8000')

# ---------------------------------------------------------------------------
# Apps
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'django.contrib.gis',
]
THIRD_PARTY_APPS = [
    'django_htmx',
]
LOCAL_APPS = [
    'apps.core',
    'apps.accounts',
    'apps.delivery',
    'apps.catalog',
    'apps.orders',
    'apps.payments',
    'apps.notifications',
    'apps.console',
]
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # เพิ่ม request.htmx ให้ view แยกได้ว่าควร render ทั้งหน้าหรือแค่ partial
    'django_htmx.middleware.HtmxMiddleware',
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.core.context_processors.site',
                'apps.orders.context_processors.cart',
                'apps.console.context_processors.console_badges',
                'apps.notifications.context_processors.notifications',
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Database: PostgreSQL + PostGIS (ตัวอย่าง URL: postgis://user:pass@127.0.0.1:5433/tmpp)
# ---------------------------------------------------------------------------
DATABASES = {
    'default': env.db_url('DATABASE_URL'),
}
# เปิด connection ค้างไว้ 60 วิ ลดเวลาต่อ DB ใหม่ทุก request
DATABASES['default']['CONN_MAX_AGE'] = env.int('DB_CONN_MAX_AGE', default=60)
DATABASES['default']['CONN_HEALTH_CHECKS'] = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ---------------------------------------------------------------------------
# Cache (Redis) — ใช้เก็บพิกัดไรเดอร์ล่าสุดและ cache ทั่วไป
# ---------------------------------------------------------------------------
REDIS_URL = env('REDIS_URL', default='redis://127.0.0.1:6380/0')
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.redis.RedisCache',
        'LOCATION': REDIS_URL,
        'KEY_PREFIX': 'tmpp',
        'TIMEOUT': 300,
    }
}

# ---------------------------------------------------------------------------
# Session: ใช้ cookie ของ Django (ไม่ใช้ JWT ในหน้าเว็บ)
# ---------------------------------------------------------------------------
SESSION_ENGINE = 'django.contrib.sessions.backends.cached_db'
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30  # 30 วัน ลูกค้าไม่ต้องล็อกอินบ่อย
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
# HTMX ส่ง CSRF token ผ่าน hx-headers ที่ <body> ใน base.html จึงปิดไม่ให้ JS อ่าน cookie ได้
CSRF_COOKIE_HTTPONLY = True

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]
AUTH_USER_MODEL = 'accounts.User'
LOGIN_URL = 'accounts:login'
LOGOUT_REDIRECT_URL = 'core:home'
# หลังล็อกอินแต่ละบทบาทไปหน้าของตัวเอง ดู accounts.services.auth_service.home_url_for()

# ล็อกอินผิดเกินจำนวนนี้ภายในช่วงเวลา -> ล็อกชั่วคราว (กันเดารหัสผ่าน)
LOGIN_MAX_FAILURES = env.int('LOGIN_MAX_FAILURES', default=5)
LOGIN_LOCKOUT_SECONDS = env.int('LOGIN_LOCKOUT_SECONDS', default=15 * 60)

# Google Sign-In: Client ID จาก Google Cloud Console (ว่าง = ซ่อนปุ่ม Google)
GOOGLE_CLIENT_ID = env('GOOGLE_CLIENT_ID', default='')

# ---------------------------------------------------------------------------
# ภาษา / เวลา
# ---------------------------------------------------------------------------
LANGUAGE_CODE = 'th'
TIME_ZONE = 'Asia/Bangkok'
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static / Media
# ---------------------------------------------------------------------------
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
# สลิปและรูปหลักฐานการส่ง: ห้ามเสิร์ฟตรง ต้องผ่าน view ที่ตรวจสิทธิ์
PRIVATE_MEDIA_ROOT = Path(env('PRIVATE_MEDIA_ROOT', default=str(BASE_DIR / 'private_media')))

FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = env('CELERY_BROKER_URL', default=REDIS_URL)
CELERY_RESULT_BACKEND = env('CELERY_RESULT_BACKEND', default=REDIS_URL)
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TIME_LIMIT = 5 * 60
CELERY_TASK_SOFT_TIME_LIMIT = 4 * 60
# ยืนยันงานหลังทำเสร็จ ถ้า worker ตายกลางทางงานจะถูกส่งใหม่ (task ต้อง idempotent)
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BEAT_SCHEDULE = {
    # ยกเลิกออเดอร์ที่ไม่จ่ายเงินเกินเวลา ทุก 1 นาที
    'expire-unpaid-orders': {'task': 'apps.payments.tasks.expire_unpaid_orders', 'schedule': 60.0},
}

# ---------------------------------------------------------------------------
# ค่าส่ง (บาท / กม.) — ลูกค้าจ่าย 30 บาท 3 กม.แรก เกินคิดกม.ละ 6 · ไรเดอร์ได้ 25 + กม.ละ 5
# ระยะทางคิดแบบเส้นตรงจากร้านถึงหมุดลูกค้า (PostGIS) ปัดเศษกม.ที่เกินขึ้น
# ---------------------------------------------------------------------------
DELIVERY_BASE_FARE = Decimal(env('DELIVERY_BASE_FARE', default='30'))
DELIVERY_BASE_DISTANCE_KM = Decimal(env('DELIVERY_BASE_DISTANCE_KM', default='3'))
DELIVERY_PER_KM_FARE = Decimal(env('DELIVERY_PER_KM_FARE', default='6'))
RIDER_BASE_EARNING = Decimal(env('RIDER_BASE_EARNING', default='25'))
RIDER_PER_KM_EARNING = Decimal(env('RIDER_PER_KM_EARNING', default='5'))
MAX_DELIVERY_DISTANCE_KM = Decimal(env('MAX_DELIVERY_DISTANCE_KM', default='15'))
CART_MAX_QUANTITY_PER_LINE = 20
CART_MAX_LINES = 30

# Google Maps JavaScript API (ว่าง = ไม่แสดงแผนที่ ลูกค้าใช้ปุ่ม "ใช้ตำแหน่งปัจจุบัน" แทน)
GOOGLE_MAPS_API_KEY = env('GOOGLE_MAPS_API_KEY', default='')

# ---------------------------------------------------------------------------
# ชำระเงิน: QR พร้อมเพย์ + ตรวจสลิปด้วย EasySlip V2
# ---------------------------------------------------------------------------
PROMPTPAY_ID = env('PROMPTPAY_ID', default='')                 # เบอร์ 10 หลัก / เลขบัตร 13 หลัก / e-Wallet 15 หลัก
SHOP_BANK_CODE = env('SHOP_BANK_CODE', default='')             # รหัสธนาคารตาม EasySlip เช่น 004 = กสิกร (ไม่บังคับ)
SHOP_BANK_ACCOUNT = env('SHOP_BANK_ACCOUNT', default='')       # เลขบัญชีที่ผูกพร้อมเพย์ (ใช้เทียบในสลิป)
SHOP_ACCOUNT_NAMES = env.list('SHOP_ACCOUNT_NAMES', default=[])  # ชื่อบัญชีผู้รับ ไทย/อังกฤษ คั่นด้วย comma
EASYSLIP_API_URL = env('EASYSLIP_API_URL', default='https://api.easyslip.com/v2/verify/bank')
EASYSLIP_API_KEY = env('EASYSLIP_API_KEY', default='')
EASYSLIP_TIMEOUT_SECONDS = env.int('EASYSLIP_TIMEOUT_SECONDS', default=20)
# AUTO = ตรวจด้วย EasySlip (ล่ม/ไม่มีคีย์ -> ส่งให้เจ้าของตรวจเอง) · MANUAL = เจ้าของตรวจทุกใบ
PAYMENT_VERIFICATION_MODE = env('PAYMENT_VERIFICATION_MODE', default='AUTO').upper()
SLIP_MAX_ATTEMPTS = env.int('SLIP_MAX_ATTEMPTS', default=3)
SLIP_MAX_BYTES = env.int('SLIP_MAX_BYTES', default=4 * 1024 * 1024)
# ไม่จ่ายภายในกี่นาทีหลังสั่ง -> ยกเลิกอัตโนมัติ (ออเดอร์ที่ส่งสลิปแล้วไม่ถูกยกเลิก)
PAYMENT_WINDOW_MINUTES = env.int('PAYMENT_WINDOW_MINUTES', default=20)

# ---------------------------------------------------------------------------
# แจ้งเตือน (Firebase Cloud Messaging)
# ---------------------------------------------------------------------------
# ไฟล์ service account (ลับ ห้าม commit) ใช้ส่งจากเซิร์ฟเวอร์ · ว่าง = บันทึกแจ้งเตือนในระบบ แต่ไม่ส่ง push
FIREBASE_CREDENTIALS_PATH = env('FIREBASE_CREDENTIALS_PATH', default='')
# ค่าฝั่งเว็บ (เปิดเผยได้ อยู่ในหน้าเว็บอยู่แล้ว) ใช้ขอ token จากเบราว์เซอร์
FIREBASE_WEB_CONFIG = {
    'apiKey': env('FIREBASE_API_KEY', default=''),
    'authDomain': env('FIREBASE_AUTH_DOMAIN', default=''),
    'projectId': env('FIREBASE_PROJECT_ID', default=''),
    'messagingSenderId': env('FIREBASE_MESSAGING_SENDER_ID', default=''),
    'appId': env('FIREBASE_APP_ID', default=''),
}
FIREBASE_VAPID_KEY = env('FIREBASE_VAPID_KEY', default='')
FIREBASE_JS_VERSION = '12.19.0'

# ---------------------------------------------------------------------------
# Django Admin: ใช้เฉพาะนักพัฒนา ไม่ใช่หลังบ้านของเจ้าของร้าน (ใช้ /console/)
# ---------------------------------------------------------------------------
DJANGO_ADMIN_ENABLED = env.bool('DJANGO_ADMIN_ENABLED', default=False)

# ---------------------------------------------------------------------------
# Logging: ออก stdout ให้ docker เก็บ
# ---------------------------------------------------------------------------
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {'format': '{asctime} {levelname} {name} {message}', 'style': '{'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'simple'},
    },
    'root': {'handlers': ['console'], 'level': 'INFO'},
    'loggers': {
        'django.db.backends': {'level': 'WARNING'},
    },
}
