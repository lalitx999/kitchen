"""
สร้างแจ้งเตือนในระบบ แล้วส่ง push ผ่าน Celery (เรียก FCM ใน request ไม่ได้ — CLAUDE.md กฎข้อ 3)
ใช้: notify(users, kind='order.paid', title='...', body='...', url='/orders/...')
"""
import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from ..models import DeviceToken, Notification

logger = logging.getLogger(__name__)


class PushNotConfigured(Exception):
    pass


def notify(users, *, kind: str, title: str, body: str, url: str = '') -> list[Notification]:
    users = [u for u in users if u is not None and u.is_active]
    if not users:
        return []
    rows = Notification.objects.bulk_create([
        Notification(user=u, kind=kind, title=title[:120], body=body[:255], url=url[:255]) for u in users
    ])
    ids = [str(n.pk) for n in rows]
    from ..tasks import send_push_task
    # ส่งหลัง commit: ถ้าการเปลี่ยนสถานะถูก rollback จะไม่มี push หลุดออกไป
    transaction.on_commit(lambda: send_push_task.delay(ids))
    return rows


# --------------------------------------------------------------------------- ส่ง push (เรียกจาก Celery)
def _messaging():
    path = settings.FIREBASE_CREDENTIALS_PATH
    if not path:
        raise PushNotConfigured('ยังไม่ได้ตั้งค่า FIREBASE_CREDENTIALS_PATH')
    import os

    if not os.path.isfile(path):
        # ตั้ง path ไว้แต่ยังไม่ได้วางไฟล์บน server -> ข้ามการส่ง ไม่ให้ task พัง
        raise PushNotConfigured(f'ไม่พบไฟล์ service account ที่ {path}')
    if not os.access(path, os.R_OK):
        raise PushNotConfigured(f'อ่านไฟล์ service account ไม่ได้ (สิทธิ์ไฟล์) ที่ {path}')
    import firebase_admin
    from firebase_admin import credentials, messaging

    try:
        firebase_admin.get_app()
    except ValueError:
        firebase_admin.initialize_app(credentials.Certificate(path))
    return messaging


def send_push(notification_ids) -> int:
    """
    idempotent: แจ้งเตือนที่ส่งแล้ว (sent_at มีค่า) ไม่ส่งซ้ำ · คืนจำนวนเครื่องที่ส่งสำเร็จ
    token ที่ FCM บอกว่าใช้ไม่ได้แล้ว (ถอนการอนุญาต/ลบแอป) จะถูกปิดอัตโนมัติ
    """
    notifications = list(Notification.objects.filter(pk__in=notification_ids, sent_at__isnull=True))
    if not notifications:
        return 0
    try:
        messaging = _messaging()
    except PushNotConfigured as exc:
        logger.info('push skipped: %s', exc)
        return 0

    user_ids = {n.user_id for n in notifications}
    tokens_by_user: dict = {}
    for user_id, token in DeviceToken.objects.filter(user_id__in=user_ids, is_active=True).values_list('user_id', 'token'):
        tokens_by_user.setdefault(user_id, []).append(token)

    delivered, dead_tokens, sent_ids = 0, [], []
    for n in notifications:
        tokens = tokens_by_user.get(n.user_id, [])
        if not tokens:
            continue
        link = f'{settings.SITE_URL}{n.url}' if n.url else settings.SITE_URL
        message = messaging.MulticastMessage(
            tokens=tokens,
            data={'title': n.title, 'body': n.body, 'url': n.url or '/', 'kind': n.kind},
            webpush=messaging.WebpushConfig(
                notification=messaging.WebpushNotification(title=n.title, body=n.body, icon='/static/img/logo-mark.svg'),
                fcm_options=messaging.WebpushFCMOptions(link=link),
            ),
        )
        try:
            result = messaging.send_each_for_multicast(message)
        except Exception:  # noqa: BLE001 - FCM ล่ม ไม่ให้ task พัง แจ้งเตือนยังอยู่ในระบบ
            logger.exception('FCM send failed for %s', n.pk)
            continue
        for token, response in zip(tokens, result.responses):
            if response.success:
                delivered += 1
            elif isinstance(response.exception, (messaging.UnregisteredError, messaging.SenderIdMismatchError)):
                dead_tokens.append(token)
        if result.success_count:
            sent_ids.append(n.pk)

    if dead_tokens:
        DeviceToken.objects.filter(token__in=dead_tokens).update(is_active=False)
    if sent_ids:
        Notification.objects.filter(pk__in=sent_ids).update(sent_at=timezone.now())
    return delivered


# --------------------------------------------------------------------------- อุปกรณ์ / อ่านแล้ว
def register_device(user, token: str, user_agent: str = '') -> DeviceToken:
    token = (token or '').strip()
    if not token or len(token) > 512:
        raise ValueError('token ไม่ถูกต้อง')
    # token เดียวกันย้ายเจ้าของได้ (เครื่องเดียวกันเปลี่ยนบัญชี) -> push ไม่ไปผิดคน
    device, _ = DeviceToken.objects.update_or_create(
        token=token, defaults={'user': user, 'is_active': True, 'user_agent': user_agent[:255]},
    )
    return device


def unregister_device(user, token: str) -> None:
    DeviceToken.objects.filter(user=user, token=token).update(is_active=False)


def mark_all_read(user) -> int:
    return Notification.objects.filter(user=user, read_at__isnull=True).update(read_at=timezone.now())


def mark_read(user, notification_id) -> Notification | None:
    n = Notification.objects.filter(user=user, pk=notification_id).first()
    if n and not n.read_at:
        n.read_at = timezone.now()
        n.save(update_fields=['read_at', 'updated_at'])
    return n
