from django.conf import settings

from ..models import Notification


def unread_count(user) -> int:
    return Notification.objects.filter(user=user, read_at__isnull=True).count()


def recent(user, limit: int = 50):
    # กรองด้วยผู้ใช้ที่ล็อกอินเสมอ
    return list(Notification.objects.filter(user=user).only('id', 'kind', 'title', 'body', 'url', 'read_at', 'created_at')[:limit])


def push_config() -> dict | None:
    """ค่าฝั่งเว็บของ Firebase (เปิดเผยได้) · ตั้งไม่ครบ = None -> ไม่แสดงปุ่มเปิดแจ้งเตือน"""
    web = settings.FIREBASE_WEB_CONFIG
    if not all(web.get(k) for k in ('apiKey', 'projectId', 'messagingSenderId', 'appId')) or not settings.FIREBASE_VAPID_KEY:
        return None
    return {**web, 'vapidKey': settings.FIREBASE_VAPID_KEY, 'sdkVersion': settings.FIREBASE_JS_VERSION}
