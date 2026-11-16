"""
งานจัดการบัญชีพนักงานจาก Console: เรียก service ของ accounts แล้วบันทึก AuditLog ทุกครั้ง
(console ไม่แตะ model User ตรงๆ ตามกฎ CLAUDE.md ข้อ 2)
"""
from django.db import transaction

from apps.accounts.services import user_service

from . import audit_service


def create_staff(request, *, role, full_name, email, phone, password, vehicle_plate=''):
    with transaction.atomic():
        user = user_service.create_staff_account(
            role=role, full_name=full_name, email=email, phone=phone,
            password=password, vehicle_plate=vehicle_plate,
        )
        audit_service.record(
            request, action='staff.create', target_type='user', target_id=user.pk,
            target_label=f'{user.full_name} ({user.get_role_display()})',
            changes={'role': [None, role], 'email': [None, user.email]},
        )
    return user


def set_staff_active(request, staff_user, *, active: bool) -> bool:
    if staff_user.pk == request.user.pk:
        raise PermissionError('ปิดบัญชีตัวเองไม่ได้')
    with transaction.atomic():
        changed = user_service.set_account_active(staff_user, active=active)
        if changed:
            audit_service.record(
                request, action='staff.activate' if active else 'staff.deactivate',
                target_type='user', target_id=staff_user.pk, target_label=staff_user.full_name,
                changes={'is_active': [not active, active]},
            )
    return changed


def reset_staff_password(request, staff_user, *, new_password: str) -> None:
    with transaction.atomic():
        user_service.set_password(staff_user, new_password)
        # ไม่เก็บรหัสผ่านใน log เด็ดขาด บันทึกแค่ว่ามีการเปลี่ยน
        audit_service.record(
            request, action='staff.password_reset', target_type='user',
            target_id=staff_user.pk, target_label=staff_user.full_name,
        )
