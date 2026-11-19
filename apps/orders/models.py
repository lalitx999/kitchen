"""
ออเดอร์: ห้ามลบ (ใช้ตรวจย้อนหลังทางเงิน) ยกเลิกได้ด้วยสถานะ CANCELLED
ชื่อ/ราคาเมนูถูกคัดลอก (snapshot) ไว้ใน OrderItem ณ ตอนสั่ง ร้านแก้ราคาทีหลังออเดอร์เก่าไม่เปลี่ยน
เปลี่ยนสถานะได้ทางเดียว: orders.services.order_service.transition_order()
"""
from decimal import Decimal

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


class CouponKind(models.TextChoices):
    AMOUNT = 'AMOUNT', 'ลดเป็นบาท'
    PERCENT = 'PERCENT', 'ลดเป็น %'
    FREE_DELIVERY = 'FREE_DELIVERY', 'ส่งฟรี'


class Coupon(UUIDModel):
    """
    คูปองส่วนลด เช่น ซื้อครบ 200 ลด 30 · ลด 10% สูงสุด 50 · ส่งฟรีเมื่อครบ 300
    ส่วนลดคิดฝั่งเซิร์ฟเวอร์ตอนสั่งเท่านั้น (orders.services.coupon_service) · ร้านรับส่วนลดเอง ค่าไรเดอร์ไม่ลด
    """

    code = models.CharField('รหัสคูปอง', max_length=30, unique=True)
    name = models.CharField('ชื่อที่ลูกค้าเห็น', max_length=120)
    kind = models.CharField('ประเภท', max_length=16, choices=CouponKind.choices, default=CouponKind.AMOUNT)
    value = models.DecimalField('มูลค่า', max_digits=8, decimal_places=2, default=Decimal('0'))
    max_discount = models.DecimalField('ลดสูงสุด (บาท)', max_digits=8, decimal_places=2, null=True, blank=True)
    min_subtotal = models.DecimalField('ยอดอาหารขั้นต่ำ', max_digits=10, decimal_places=2, default=Decimal('0'))
    starts_at = models.DateTimeField('เริ่มใช้', null=True, blank=True)
    ends_at = models.DateTimeField('หมดอายุ', null=True, blank=True)
    usage_limit = models.PositiveIntegerField('ใช้ได้ทั้งหมดกี่ครั้ง', null=True, blank=True)
    per_customer_limit = models.PositiveSmallIntegerField('ต่อลูกค้า 1 คน (0 = ไม่จำกัด)', default=1)
    # ว่าง = ใช้ได้ทุกสาขา
    branch = models.ForeignKey('catalog.Branch', verbose_name='สาขา', null=True, blank=True,
                               on_delete=models.CASCADE, related_name='coupons')
    show_in_checkout = models.BooleanField('แสดงให้ลูกค้าเลือกในหน้าชำระเงิน', default=True)
    is_active = models.BooleanField('เปิดใช้งาน', default=True)

    class Meta:
        db_table = 'coupons'
        ordering = ['-created_at']

    def __str__(self):
        return self.code

    @property
    def summary(self) -> str:
        if self.kind == CouponKind.FREE_DELIVERY:
            text = 'ส่งฟรี'
        elif self.kind == CouponKind.PERCENT:
            text = f'ลด {self.value:g}%' + (f' สูงสุด ฿{self.max_discount:g}' if self.max_discount else '')
        else:
            text = f'ลด ฿{self.value:g}'
        if self.min_subtotal:
            text += f' เมื่อสั่งครบ ฿{self.min_subtotal:g}'
        return text


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
    # ส่วนลดจากคูปอง: total = subtotal + delivery_fee - discount · เก็บรหัสไว้แม้คูปองถูกลบภายหลัง
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    coupon = models.ForeignKey(Coupon, null=True, blank=True, on_delete=models.SET_NULL, related_name='orders')
    coupon_code = models.CharField(max_length=30, blank=True)
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
    # ไรเดอร์กด "ถึงร้านแล้ว" (ไม่ใช่สถานะออเดอร์ แค่บอกครัวว่ามีคนรออยู่) · คืนงาน = ล้างค่า
    rider_arrived_at = models.DateTimeField(null=True, blank=True)
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
