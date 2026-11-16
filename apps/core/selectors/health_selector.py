from django.core.cache import cache
from django.db import connection


def check_dependencies() -> dict[str, bool]:
    """ตรวจว่า DB และ Redis ตอบสนอง ใช้กับ /healthz/ ให้ Caddy/Docker รู้ว่าระบบพร้อม"""
    status = {'database': False, 'cache': False}
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
        status['database'] = True
    except Exception:  # noqa: BLE001 - health check ต้องไม่ทำให้ view พัง
        pass
    try:
        cache.set('healthz', '1', timeout=5)
        status['cache'] = cache.get('healthz') == '1'
    except Exception:  # noqa: BLE001
        pass
    return status
