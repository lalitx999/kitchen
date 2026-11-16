"""
บันทึกทุกการแก้ไขที่ทำจาก Console (ใครทำอะไร กับอะไร เมื่อไร ก่อน/หลังเป็นอย่างไร)
ห้ามแก้หรือลบแถว ใช้ตรวจย้อนหลังเมื่อมีปัญหา
"""
from django.conf import settings
from django.db import models

from apps.core.models import UUIDModel


class AuditLog(UUIDModel):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='audit_logs'
    )
    action = models.CharField(max_length=64, db_index=True)   # เช่น staff.create, staff.deactivate
    target_type = models.CharField(max_length=64)              # เช่น user, menu_item
    target_id = models.CharField(max_length=64, db_index=True)
    target_label = models.CharField(max_length=255, blank=True)  # ชื่อที่อ่านง่าย ณ ตอนบันทึก
    changes = models.JSONField(default=dict, blank=True)       # {"field": [ก่อน, หลัง]}
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = 'audit_logs'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.action} {self.target_type}:{self.target_id}'
