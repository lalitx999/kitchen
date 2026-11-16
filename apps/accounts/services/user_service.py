"""แก้ไขบัญชีผู้ใช้ และสร้าง/ปิดบัญชีพนักงาน (console เรียกผ่านไฟล์นี้)"""
from django.db import IntegrityError, transaction

from apps.delivery.services import rider_service

from ..models import STAFF_ROLES, Role, User, normalize_email_address
from .auth_service import EmailAlreadyUsed


def update_profile(user: User, *, full_name: str, phone: str) -> dict:
    """คืนรายการ field ที่เปลี่ยน {field: [ก่อน, หลัง]}"""
    changes = {}
    for field, value in (('full_name', full_name.strip()), ('phone', phone)):
        if getattr(user, field) != value:
            changes[field] = [getattr(user, field), value]
            setattr(user, field, value)
    if changes:
        user.save(update_fields=[*changes, 'updated_at'])
    return changes


def create_staff_account(
    *, role: str, full_name: str, email: str, phone: str, password: str, vehicle_plate: str = ''
) -> User:
    if role not in STAFF_ROLES:
        raise ValueError(f'สร้างบัญชีพนักงานได้เฉพาะ {STAFF_ROLES}')
    try:
        with transaction.atomic():
            user = User.objects.create_user(
                email=normalize_email_address(email), password=password,
                full_name=full_name.strip(), phone=phone, role=role,
            )
            if role == Role.RIDER:
                rider_service.create_rider_profile(user, vehicle_plate=vehicle_plate)
    except IntegrityError as exc:
        raise EmailAlreadyUsed from exc
    return user


def set_account_active(user: User, *, active: bool) -> bool:
    """
    คืน True ถ้าสถานะเปลี่ยนจริง
    ปิดบัญชีแล้ว session เดิมใช้ไม่ได้ทันที (ModelBackend ไม่คืน user ที่ is_active=False)
    """
    if user.is_active == active:
        return False
    with transaction.atomic():
        user.is_active = active
        user.save(update_fields=['is_active', 'updated_at'])
        if not active and user.role == Role.RIDER:
            rider_service.force_offline(user)
    return True


def set_password(user: User, raw_password: str) -> None:
    # เปลี่ยนรหัสผ่าน = session เก่าของบัญชีนั้นหลุดทั้งหมด (Django ตรวจ hash ของรหัสผ่านใน session)
    user.set_password(raw_password)
    user.save(update_fields=['password', 'updated_at'])
