"""
ข้อมูลไรเดอร์ (1 ผู้ใช้ role RIDER = 1 RiderProfile)
พิกัดล่าสุดแบบสดเก็บใน cache (Redis บน server) ส่วน current_location ในฐานข้อมูลเขียนไม่เกินนาทีละครั้ง
"""
from django.conf import settings
from django.contrib.gis.db import models as gis_models
from django.db import models

from apps.core.models import UUIDModel
from apps.core.storage import get_private_storage


class RiderProfile(UUIDModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='rider_profile'
    )
    vehicle_plate = models.CharField('ทะเบียนรถ', max_length=20, blank=True)
    is_online = models.BooleanField('เปิดรับงาน', default=False, db_index=True)
    online_since = models.DateTimeField(null=True, blank=True)
    current_location = gis_models.PointField(srid=4326, null=True, blank=True, spatial_index=True)
    location_updated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'rider_profiles'

    def __str__(self):
        return f'Rider {self.user_id} ({"online" if self.is_online else "offline"})'


def proof_upload_path(instance, filename):
    ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else 'jpg'
    return f'delivery-proofs/{instance.proof.order_id}/{instance.id}.{ext}'


MAX_PROOF_PHOTOS = 4


class DeliveryProof(UUIDModel):
    """รูปถ่ายตอนส่งสำเร็จ (ไฟล์ส่วนตัว ดูได้เฉพาะเจ้าของร้าน/ลูกค้าเจ้าของออเดอร์/ไรเดอร์คนส่ง)"""

    order = models.OneToOneField('orders.Order', on_delete=models.PROTECT, related_name='delivery_proof')
    rider = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='delivery_proofs')
    # พิกัดไรเดอร์ตอนกดส่งสำเร็จ (ถ้ามี) ใช้ตรวจย้อนหลังเมื่อลูกค้าบอกว่าไม่ได้รับของ
    location = gis_models.PointField(srid=4326, null=True, blank=True)
    distance_to_customer_m = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        db_table = 'delivery_proofs'

    def __str__(self):
        return f'Proof {self.order_id}'


class DeliveryProofPhoto(UUIDModel):
    """รูปหลักฐาน 1-4 รูปต่อการส่ง 1 ครั้ง (เช่น หน้าบ้าน, ของในมือลูกค้า, เลขห้อง)"""

    proof = models.ForeignKey(DeliveryProof, on_delete=models.CASCADE, related_name='photos')
    photo = models.FileField(upload_to=proof_upload_path, storage=get_private_storage)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = 'delivery_proof_photos'
        ordering = ['sort_order', 'created_at']

    def __str__(self):
        return f'ProofPhoto {self.proof_id}#{self.sort_order}'


class RiderPayout(UUIDModel):
    """
    เจ้าของร้านจ่ายค่าส่งให้ไรเดอร์ 1 ครั้ง (ระบบไม่โอนเงิน แค่บันทึกว่าจ่ายแล้ว)
    ออเดอร์ที่รวมในรอบนี้ถูกผูกด้วย Order.rider_payout -> นับซ้ำในรอบหน้าไม่ได้
    """

    rider = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='payouts')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    job_count = models.PositiveIntegerField()
    first_job_at = models.DateTimeField(null=True, blank=True)
    last_job_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField('หมายเหตุ', max_length=255, blank=True)   # เช่น โอนเข้าบัญชี / เงินสด
    paid_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='+')

    class Meta:
        db_table = 'rider_payouts'
        ordering = ['-created_at']

    def __str__(self):
        return f'Payout {self.rider_id} {self.amount}'
