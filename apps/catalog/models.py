"""
ร้าน (สาขา) และเมนู
ตอนนี้มีสาขาเดียว แต่ออกแบบให้เมนูผูกกับสาขา เพิ่มสาขาได้โดยไม่ต้องแก้โครงสร้าง
"""
from decimal import Decimal

from django.contrib.gis.db import models as gis_models
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import UUIDModel


class Branch(UUIDModel):
    name = models.CharField('ชื่อร้าน/สาขา', max_length=120)
    phone = models.CharField('เบอร์ร้าน', max_length=10, blank=True)
    address = models.TextField('ที่อยู่ร้าน', blank=True)
    # พิกัดจริงของร้าน ใช้คิดระยะส่ง ไม่มีพิกัด = ยังเปิดรับออเดอร์ไม่ได้ (ไม่มีพิกัดสำรอง)
    location = gis_models.PointField(srid=4326, null=True, blank=True)
    opens_at = models.TimeField('เวลาเปิด', null=True, blank=True)
    closes_at = models.TimeField('เวลาปิด', null=True, blank=True)
    # สวิตช์ที่เจ้าของ/ครัวกดเองได้ทันที เช่น ของหมด ปิดก่อนเวลา
    is_open = models.BooleanField('เปิดรับออเดอร์', default=False)
    is_active = models.BooleanField('ใช้งาน', default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = 'branches'
        ordering = ['sort_order', 'created_at']

    def __str__(self):
        return self.name


class Category(UUIDModel):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='categories')
    name = models.CharField('ชื่อหมวด', max_length=80)
    sort_order = models.PositiveSmallIntegerField('ลำดับ', default=0)

    class Meta:
        db_table = 'menu_categories'
        ordering = ['sort_order', 'name']
        constraints = [
            models.UniqueConstraint(fields=['branch', 'name'], name='category_unique_name_per_branch'),
        ]

    def __str__(self):
        return self.name


def menu_image_path(instance, filename):
    ext = filename.rsplit('.', 1)[-1].lower()
    return f'menu/{instance.branch_id}/{instance.id}.{ext}'


class MenuItem(UUIDModel):
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name='menu_items')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='items')
    name = models.CharField('ชื่อเมนู', max_length=120)
    description = models.CharField('รายละเอียด', max_length=255, blank=True)
    price = models.DecimalField('ราคา', max_digits=8, decimal_places=2, validators=[MinValueValidator(Decimal('0'))])
    image = models.ImageField('รูป', upload_to=menu_image_path, blank=True)
    is_available = models.BooleanField('มีขาย', default=True, db_index=True)
    sort_order = models.PositiveSmallIntegerField('ลำดับ', default=0)

    class Meta:
        db_table = 'menu_items'
        ordering = ['sort_order', 'name']
        indexes = [models.Index(fields=['branch', 'is_available'])]

    def __str__(self):
        return self.name


class MenuOption(UUIDModel):
    """ตัวเลือกเสริม เลือกได้หลายอัน เช่น ไข่ดาว +10, พิเศษ +15"""

    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, related_name='options')
    name = models.CharField('ชื่อตัวเลือก', max_length=80)
    extra_price = models.DecimalField(
        'ราคาเพิ่ม', max_digits=8, decimal_places=2, default=Decimal('0'),
        validators=[MinValueValidator(Decimal('0'))],
    )
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = 'menu_options'
        ordering = ['sort_order', 'created_at']

    def __str__(self):
        return f'{self.name} (+{self.extra_price})'
