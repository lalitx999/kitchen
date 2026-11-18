"""
ผู้ใช้ทุกบทบาทอยู่ตารางเดียว แยกด้วย role
- CUSTOMER สมัครเองได้ (อีเมล/รหัสผ่าน หรือ Google)
- KITCHEN / RIDER เจ้าของร้านสร้างให้ใน Console เท่านั้น
- OWNER สร้างด้วยคำสั่ง `python manage.py create_owner`
"""
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.contrib.gis.db import models as gis_models
from django.db import models
from django.db.models.functions import Lower

from apps.core.models import UUIDModel


class Role(models.TextChoices):
    CUSTOMER = 'CUSTOMER', 'ลูกค้า'
    KITCHEN = 'KITCHEN', 'ครัว'
    RIDER = 'RIDER', 'ไรเดอร์'
    OWNER = 'OWNER', 'เจ้าของร้าน'


STAFF_ROLES = (Role.KITCHEN, Role.RIDER)


def normalize_email_address(email: str) -> str:
    # ตัดช่องว่างและทำเป็นตัวเล็กทั้งหมด กันสมัครซ้ำด้วย A@x.com กับ a@x.com
    return (email or '').strip().lower()


class UserManager(BaseUserManager):
    use_in_migrations = True

    def get_by_natural_key(self, email):
        # ModelBackend เรียกตอนล็อกอิน: ค้นแบบไม่สนตัวพิมพ์
        return self.get(email__iexact=normalize_email_address(email))

    def _create_user(self, email, password, **extra_fields):
        if not email:
            raise ValueError('ต้องมีอีเมล')
        user = self.model(email=normalize_email_address(email), **extra_fields)
        if password:
            user.set_password(password)
        else:
            # บัญชีที่สร้างจาก Google ไม่มีรหัสผ่าน ล็อกอินด้วยรหัสผ่านไม่ได้จนกว่าจะตั้ง
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault('role', Role.CUSTOMER)
        extra_fields.setdefault('is_staff', False)
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        # superuser = นักพัฒนา (Django Admin) ไม่ใช่เจ้าของร้าน แต่ให้ role OWNER เพื่อเข้า console ได้
        extra_fields.setdefault('role', Role.OWNER)
        extra_fields['is_staff'] = True
        extra_fields['is_superuser'] = True
        return self._create_user(email, password, **extra_fields)


class User(UUIDModel, AbstractBaseUser, PermissionsMixin):
    email = models.EmailField('อีเมล', unique=True)
    full_name = models.CharField('ชื่อ', max_length=150)
    phone = models.CharField('เบอร์โทร', max_length=10, blank=True)
    role = models.CharField('บทบาท', max_length=16, choices=Role.choices, default=Role.CUSTOMER, db_index=True)
    google_sub = models.CharField(max_length=64, unique=True, null=True, blank=True, editable=False)
    is_active = models.BooleanField('ใช้งานได้', default=True)
    # is_staff = เข้า Django Admin ได้ (นักพัฒนาเท่านั้น) ไม่เกี่ยวกับพนักงานร้าน
    is_staff = models.BooleanField(default=False)
    # พนักงานครัวผูกกับ 1 สาขา (เห็นเฉพาะออเดอร์/เมนูสาขานั้น) · ว่าง = สาขาหลัก
    # เจ้าของเลือกสาขาจาก Console ได้ทุกสาขา · ไรเดอร์ใช้ร่วมกันทุกสาขา จึงไม่ใช้ฟิลด์นี้
    branch = models.ForeignKey('catalog.Branch', verbose_name='สาขา', null=True, blank=True,
                               on_delete=models.SET_NULL, related_name='staff')

    objects = UserManager()

    USERNAME_FIELD = 'email'
    EMAIL_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']

    class Meta:
        db_table = 'users'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(Lower('email'), name='users_email_ci_unique'),
        ]

    def __str__(self):
        return f'{self.full_name} <{self.email}>'

    def get_full_name(self):
        return self.full_name

    def get_short_name(self):
        return self.full_name.split(' ')[0] if self.full_name else self.email

    @property
    def is_customer(self) -> bool:
        return self.role == Role.CUSTOMER

    @property
    def is_rider(self) -> bool:
        return self.role == Role.RIDER

    @property
    def is_owner(self) -> bool:
        return self.role == Role.OWNER

    @property
    def is_kitchen(self) -> bool:
        return self.role == Role.KITCHEN


class CustomerAddress(UUIDModel):
    """ที่อยู่ที่ลูกค้าเคยใช้ส่ง (บันทึกอัตโนมัติตอนสั่ง ครั้งหน้าเลือกได้เลย)"""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='addresses')
    label = models.CharField('ชื่อที่อยู่', max_length=40, blank=True)  # เช่น บ้าน, ที่ทำงาน
    address_text = models.TextField('ที่อยู่')
    note = models.CharField('จุดสังเกต', max_length=255, blank=True)
    location = gis_models.PointField(srid=4326)
    last_used_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'customer_addresses'
        ordering = ['-last_used_at']

    def __str__(self):
        return self.label or self.address_text[:30]
