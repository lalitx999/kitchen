"""
โมเดลฐานที่ทุก app สืบทอด (abstract ไม่สร้างตาราง)
ใช้ UUID เป็น primary key เพื่อไม่ให้เดาเลขออเดอร์/ผู้ใช้ถัดไปจาก URL ได้
"""
import uuid

from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UUIDModel(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True
