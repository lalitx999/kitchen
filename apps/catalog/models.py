"""
ร้าน (สาขา) และเมนู
ตอนนี้มีสาขาเดียว แต่ออกแบบให้เมนูผูกกับสาขา เพิ่มสาขาได้โดยไม่ต้องแก้โครงสร้าง
"""
import uuid
from decimal import Decimal

from django.contrib.gis.db import models as gis_models
from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import UUIDModel


def branch_image_path(instance, filename):
    # ชื่อไฟล์สุ่มใหม่ทุกครั้ง: เปลี่ยนรูปแล้ว cache ของ Caddy/เบราว์เซอร์ไม่ค้างรูปเก่า
    ext = filename.rsplit('.', 1)[-1].lower()
    return f'branch/{instance.id}/{uuid.uuid4().hex[:12]}.{ext}'


def _baht(default, label):
    return models.DecimalField(label, max_digits=7, decimal_places=2, default=Decimal(default),
                               validators=[MinValueValidator(Decimal('0'))])


class Branch(UUIDModel):
    name = models.CharField('ชื่อร้าน/สาขา', max_length=120)
    phone = models.CharField('เบอร์ร้าน', max_length=10, blank=True)
    address = models.TextField('ที่อยู่ร้าน', blank=True)
    # เจ้าของวางลิงก์ Google Maps -> ระบบดึงพิกัดมาเก็บใน location
    maps_url = models.URLField('ลิงก์ Google Maps', max_length=500, blank=True)
    # พิกัดจริงของร้าน ใช้คิดระยะส่ง ไม่มีพิกัด = ยังเปิดรับออเดอร์ไม่ได้ (ไม่มีพิกัดสำรอง)
    location = gis_models.PointField(srid=4326, null=True, blank=True)
    storefront_image = models.ImageField('ภาพหน้าร้าน', upload_to=branch_image_path, blank=True)
    cover_image = models.ImageField('ภาพปกร้าน', upload_to=branch_image_path, blank=True)

    # ค่าส่ง: ลูกค้าจ่าย / ไรเดอร์ได้ ส่วนต่าง = ร้านได้ · ตั้งต่อสาขา (รองรับหลายสาขาในอนาคต)
    delivery_base_km = models.DecimalField('ระยะเหมา (กม.)', max_digits=5, decimal_places=2, default=Decimal('3'),
                                           validators=[MinValueValidator(Decimal('0'))])
    delivery_base_fare = _baht('30', 'ค่าส่งช่วงเหมา')
    delivery_per_km_fare = _baht('6', 'ค่าส่งต่อ กม. ถัดไป')
    rider_base_fare = _baht('25', 'ไรเดอร์ได้ช่วงเหมา')
    rider_per_km_fare = _baht('5', 'ไรเดอร์ได้ต่อ กม. ถัดไป')
    max_delivery_km = models.DecimalField('ส่งไกลสุด (กม.)', max_digits=5, decimal_places=2, default=Decimal('15'),
                                          validators=[MinValueValidator(Decimal('0'))])
    opens_at = models.TimeField('เวลาเปิด', null=True, blank=True)
    closes_at = models.TimeField('เวลาปิด', null=True, blank=True)
    # สวิตช์ที่เจ้าของ/ครัวกดเองได้ทันที เช่น ของหมด ปิดก่อนเวลา
    # จอครัว: สีหัวใบออเดอร์ตามเวลารอ (นาทีนับจากลูกค้าจ่ายเงิน) เขียว -> ส้ม (ถึง warn) -> แดง (ถึง late)
    kitchen_warn_minutes = models.PositiveSmallIntegerField('ครัว: เริ่มเตือน (นาที)', default=10)
    kitchen_late_minutes = models.PositiveSmallIntegerField('ครัว: ช้า (นาที)', default=15)
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

    def option_sections(self) -> list[dict]:
        """
        ตัวเลือกจัดเป็นกลุ่มสำหรับแสดงผล (ใช้ข้อมูลที่ prefetch มาแล้ว ไม่ query เพิ่ม)
        ตัวเลือกที่ไม่มีกลุ่มรวมไว้ท้ายสุด ชื่อ "ตัวเลือกเพิ่มเติม" เลือกได้ไม่จำกัด
        """
        options = list(self.options.all())
        sections = [{'group': g, 'options': [o for o in options if o.group_id == g.pk]}
                    for g in self.option_groups.all()]
        loose = [o for o in options if o.group_id is None]
        if loose:
            sections.append({'group': None, 'options': loose})
        return [s for s in sections if s['options']]

    def empty_option_groups(self) -> list:
        """กลุ่มที่ยังไม่มีตัวเลือก (ลูกค้ายังไม่เห็น) แสดงเตือนใน Console"""
        used = {o.group_id for o in self.options.all()}
        return [g for g in self.option_groups.all() if g.pk not in used]


class MenuOptionGroup(UUIDModel):
    """
    กลุ่มตัวเลือก เช่น "เลือกเนื้อ" (ต้องเลือก 1) · "ท็อปปิ้ง" (ไม่บังคับ เลือกได้สูงสุด 3)
    min_select = 0 คือไม่บังคับ · ตรวจซ้ำที่เซิร์ฟเวอร์ตอนใส่ตะกร้า (ไม่เชื่อหน้าเว็บ)
    """

    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, related_name='option_groups')
    name = models.CharField('ชื่อกลุ่ม', max_length=80)
    min_select = models.PositiveSmallIntegerField('ต้องเลือกอย่างน้อย', default=0)
    max_select = models.PositiveSmallIntegerField('เลือกได้สูงสุด', default=1)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = 'menu_option_groups'
        ordering = ['sort_order', 'created_at']

    def __str__(self):
        return self.name

    @property
    def is_required(self) -> bool:
        return self.min_select > 0

    @property
    def rule_label(self) -> str:
        if self.min_select and self.min_select == self.max_select:
            return f'ต้องเลือก {self.min_select}'
        if self.min_select:
            return f'ต้องเลือก {self.min_select}-{self.max_select}'
        return f'ไม่จำเป็นต้องระบุ, สูงสุด {self.max_select}'


class MenuOption(UUIDModel):
    """ตัวเลือกเสริม เช่น ไข่ดาว +10 · อยู่ในกลุ่มหรือไม่มีกลุ่มก็ได้ (ไม่มีกลุ่ม = เลือกได้หลายอัน)"""

    menu_item = models.ForeignKey(MenuItem, on_delete=models.CASCADE, related_name='options')
    group = models.ForeignKey(MenuOptionGroup, on_delete=models.CASCADE, null=True, blank=True, related_name='choices')
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
