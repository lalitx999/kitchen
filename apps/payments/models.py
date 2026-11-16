"""
สลิปโอนเงิน 1 ใบ = 1 แถว (ลูกค้าแนบใหม่ได้ถ้าใบก่อนไม่ผ่าน ไม่เกิน SLIP_MAX_ATTEMPTS)
กันสลิปซ้ำ 2 ชั้น: trans_ref (รหัสธุรกรรมจากธนาคาร) unique เมื่ออนุมัติ + hash ของไฟล์
"""
from django.conf import settings
from django.db import models
from django.db.models import Q

from apps.core.models import UUIDModel
from apps.core.storage import get_private_storage


class SlipStatus(models.TextChoices):
    PROCESSING = 'PROCESSING', 'กำลังตรวจอัตโนมัติ'
    NEEDS_REVIEW = 'NEEDS_REVIEW', 'รอเจ้าของร้านตรวจ'
    APPROVED = 'APPROVED', 'ผ่าน'
    REJECTED = 'REJECTED', 'ไม่ผ่าน'


class ReviewSource(models.TextChoices):
    AUTO = 'AUTO', 'EasySlip'
    MANUAL = 'MANUAL', 'เจ้าของร้านตรวจ'


def slip_upload_path(instance, filename):
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'jpg'
    return f'slips/{instance.order_id}/{instance.id}.{ext}'


class SlipTransaction(UUIDModel):
    order = models.ForeignKey('orders.Order', on_delete=models.PROTECT, related_name='slips')
    attempt_no = models.PositiveSmallIntegerField()
    image = models.FileField(upload_to=slip_upload_path, storage=get_private_storage)
    image_sha256 = models.CharField(max_length=64, db_index=True)
    status = models.CharField(max_length=16, choices=SlipStatus.choices, default=SlipStatus.PROCESSING, db_index=True)
    reason = models.CharField('เหตุผล', max_length=255, blank=True)   # แสดงให้ลูกค้าเห็นได้

    # ข้อมูลที่อ่านได้จากสลิป
    trans_ref = models.CharField(max_length=64, null=True, blank=True)
    amount_read = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    sender_name = models.CharField(max_length=150, blank=True)
    provider_payload = models.JSONField(default=dict, blank=True)

    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='+')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_source = models.CharField(max_length=8, choices=ReviewSource.choices, blank=True)

    class Meta:
        db_table = 'payment_slips'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['order', 'attempt_no'], name='slip_unique_attempt_per_order'),
            # สลิปเดียวกัน (รหัสธุรกรรมเดียวกัน) อนุมัติได้ครั้งเดียวทั้งระบบ แม้สองคนส่งพร้อมกัน
            models.UniqueConstraint(fields=['trans_ref'], condition=Q(status='APPROVED'), name='slip_unique_approved_trans_ref'),
        ]

    def __str__(self):
        return f'Slip {self.order_id} #{self.attempt_no} ({self.status})'
