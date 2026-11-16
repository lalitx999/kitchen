from django.conf import settings
from django.contrib.gis.geos import Point
from django.db import transaction

from ..models import Branch
from ..selectors.menu_selector import get_storefront_branch


def get_or_create_main_branch() -> Branch:
    """เจ้าของเปิด Console ครั้งแรก ยังไม่มีร้าน -> สร้างร้านหลัก (ยังไม่มีพิกัด ยังไม่เปิดรับออเดอร์)"""
    branch = get_storefront_branch()
    if branch is None:
        with transaction.atomic():
            branch = get_storefront_branch() or Branch.objects.create(name=settings.SITE_NAME, is_open=False)
    return branch


def _point_label(point):
    return f'{point.y:.6f},{point.x:.6f}' if point else None


def update_branch(branch: Branch, *, name, phone, address, latitude, longitude, opens_at, closes_at) -> dict:
    """คืน {field: [ก่อน, หลัง]} สำหรับบันทึก AuditLog"""
    new_location = Point(float(longitude), float(latitude), srid=4326) if latitude is not None else None
    new_values = {
        'name': name.strip(), 'phone': phone, 'address': address.strip(),
        'opens_at': opens_at, 'closes_at': closes_at,
    }
    changes = {}
    for field, value in new_values.items():
        if getattr(branch, field) != value:
            changes[field] = [str(getattr(branch, field) or ''), str(value or '')]
            setattr(branch, field, value)
    if _point_label(branch.location) != _point_label(new_location):
        changes['location'] = [_point_label(branch.location), _point_label(new_location)]
        branch.location = new_location
    if changes:
        branch.save()
    return changes


def set_open(branch: Branch, *, is_open: bool) -> bool:
    if branch.is_open == is_open:
        return False
    branch.is_open = is_open
    branch.save(update_fields=['is_open', 'updated_at'])
    return True
