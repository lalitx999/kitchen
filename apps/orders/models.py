"""
ออเดอร์: ห้ามลบ (ใช้ตรวจย้อนหลังทางเงิน) ยกเลิกได้ด้วยสถานะ CANCELLED
ชื่อ/ราคาเมนูถูกคัดลอก (snapshot) ไว้ใน OrderItem ณ ตอนสั่ง ร้านแก้ราคาทีหลังออเดอร์เก่าไม่เปลี่ยน
เปลี่ยนสถานะได้ทางเดียว: orders.services.order_service.transition_order()
"""
from django.conf import settings
from django.contrib.gis.db import models as gis_models
from django.db import models

from apps.core.models import UUIDModel


class OrderStatus(models.TextChoices):
    PENDING_PAYMENT = 'PENDING_PAYMENT', 'รอชำระเงิน'
    PAYMENT_REVIEW = 'PAYMENT_REVIEW', 'รอตรวจสลิป'
    PAID = 'PAID', 'ชำระแล้ว รอครัวรับ'
    PREPARING = 'PREPARING', 'กำลังทำอาหาร'
    READY = 'READY', 'อาหารพร้อมส่ง'
    DELIVERING = 'DELIVERING', 'กำลังไปส่ง'
    COMPLETED = 'COMPLETED', 'ส่งสำเร็จ'
    CANCELLED = 'CANCELLED', 'ยกเลิก'


# สถานะที่ลูกค้ายังต้องติดตาม (ใช้ทำ polling และนับ "ออเดอร์ที่ยังไม่จบ")
ACTIVE_STATUSES = (
    OrderStatus.PENDING_PAYMENT, OrderStatus.PAYMENT_REVIEW, OrderStatus.PAID,
    OrderStatus.PREPARING, OrderStatus.READY, OrderStatus.DELIVERING,
)


class Order(UUIDModel):
    order_number = models.CharField(max_length=20, unique=True)
    customer = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='orders')
    branch = models.ForeignKey('catalog.Branch', on_delete=models.PROTECT, related_name='orders')
    rider = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name='rider_orders'
    )
    status = models.CharField(max_length=20, choices=OrderStatus.choices, default=OrderStatus.PENDING_PAYMENT, db_index=True)

    # เงิน (Decimal เสมอ คิดฝั่งเซิร์ฟเวอร์)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)
    delivery_fee = models.DecimalField(max_digits=8, decimal_places=2)
    total = models.DecimalField(max_digits=10, decimal_places=2)
    rider_fee = models.DecimalField(max_digits=8, decimal_places=2)  # ส่วนของไรเดอร์ (D3) เจ้าของจ่ายเอง
    distance_km = models.DecimalField(max_digits=6, decimal_places=2)

    # ผู้รับ (snapshot ณ ตอนสั่ง)
    recipient_name = models.CharField(max_length=150)
    recipient_phone = models.CharField(max_length=10)
    address_text = models.TextField()
    address_note = models.CharField(max_length=255, blank=True)
    delivery_location = gis_models.PointField(srid=4326)
    note = models.CharField('หมายเหตุถึงร้าน', max_length=255, blank=True)

    cancelled_reason = models.CharField(max_length=255, blank=True)
    rider_assigned_at = models.DateTimeField(null=True, blank=True)
    # จ่ายค่าส่งให้ไรเดอร์แล้วในรอบไหน (ว่าง = ยังไม่จ่าย)
    rider_payout = models.ForeignKey('delivery.RiderPayout', on_delete=models.PROTECT, null=True, blank=True,
                                     related_name='orders')
    picked_up_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'orders'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['customer', '-created_at']),
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        return f'{self.order_number} ({self.status})'

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_STATUSES

    @property
    def can_customer_cancel(self) -> bool:
        return self.status == OrderStatus.PENDING_PAYMENT


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    # เมนูถูกลบได้ ประวัติยังอยู่เพราะเก็บชื่อ/ราคาไว้แล้ว
    menu_item = models.ForeignKey('catalog.MenuItem', on_delete=models.SET_NULL, null=True, related_name='+')
    name = models.CharField(max_length=120)
    unit_price = models.DecimalField(max_digits=8, decimal_places=2)  # ราคาเมนู + ตัวเลือกแล้ว
    options = models.JSONField(default=list)  # [{"name": "ไข่ดาว", "extra_price": "10.00"}]
    quantity = models.PositiveSmallIntegerField()
    line_total = models.DecimalField(max_digits=10, decimal_places=2)
    note = models.CharField(max_length=120, blank=True)

    class Meta:
        db_table = 'order_items'
        ordering = ['id']

    def __str__(self):
        return f'{self.name} x{self.quantity}'


class OrderStatusLog(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='status_logs')
    from_status = models.CharField(max_length=20, choices=OrderStatus.choices, blank=True)
    to_status = models.CharField(max_length=20, choices=OrderStatus.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='+')
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'order_status_logs'
        ordering = ['created_at', 'id']

    def __str__(self):
        return f'{self.order_id}: {self.from_status or "-"} -> {self.to_status}'
