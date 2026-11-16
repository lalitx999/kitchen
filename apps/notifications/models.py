"""
แจ้งเตือน 2 ทาง
1. Notification: เก็บในระบบเสมอ (เห็นในหน้า "แจ้งเตือน" ของเว็บ แม้ไม่ได้เปิด push)
2. push ผ่าน FCM ไปยังทุกเครื่องที่ผู้ใช้กดอนุญาต (DeviceToken)
"""
from django.conf import settings
from django.db import models

from apps.core.models import UUIDModel


class DeviceToken(UUIDModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='device_tokens')
    token = models.CharField(max_length=512, unique=True)
    user_agent = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    last_seen_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'device_tokens'

    def __str__(self):
        return f'Device {self.user_id} ({"active" if self.is_active else "inactive"})'


class Notification(UUIDModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    kind = models.CharField(max_length=40, db_index=True)   # เช่น order.paid, slip.review, job.new
    title = models.CharField(max_length=120)
    body = models.CharField(max_length=255)
    url = models.CharField(max_length=255, blank=True)      # path ในเว็บเรา เมื่อกดแจ้งเตือน
    read_at = models.DateTimeField(null=True, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)   # ส่ง push สำเร็จอย่างน้อย 1 เครื่อง

    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', 'read_at'])]

    def __str__(self):
        return f'{self.kind} -> {self.user_id}'
