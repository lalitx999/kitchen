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


TEXT_FIELDS = ('name', 'phone', 'address', 'maps_url')
VALUE_FIELDS = ('opens_at', 'closes_at', 'delivery_base_km', 'delivery_base_fare', 'delivery_per_km_fare',
                'rider_base_fare', 'rider_per_km_fare', 'max_delivery_km')
IMAGE_FIELDS = ('storefront_image', 'cover_image')


def update_branch(branch: Branch, *, latitude, longitude, images=None, remove_images=(), **values) -> dict:
    """
    คืน {field: [ก่อน, หลัง]} สำหรับบันทึก AuditLog
    images: {'cover_image': ไฟล์ใหม่} · remove_images: ชื่อฟิลด์รูปที่ต้องการลบ
    """
    images = images or {}
    changes = {}
    for field in TEXT_FIELDS + VALUE_FIELDS:
        if field not in values:
            continue
        value = values[field].strip() if field in TEXT_FIELDS else values[field]
        if getattr(branch, field) != value:
            changes[field] = [str(getattr(branch, field) or ''), str(value or '')]
            setattr(branch, field, value)

    new_location = Point(float(longitude), float(latitude), srid=4326) if latitude is not None else None
    if _point_label(branch.location) != _point_label(new_location):
        changes['location'] = [_point_label(branch.location), _point_label(new_location)]
        branch.location = new_location

    old_files = []
    for field in IMAGE_FIELDS:
        current = getattr(branch, field)
        if images.get(field):
            if current:
                old_files.append(current.name)
            setattr(branch, field, images[field])
            changes[field] = ['มีรูป' if current else '', 'อัปโหลดรูปใหม่']
        elif field in remove_images and current:
            old_files.append(current.name)
            setattr(branch, field, '')
            changes[field] = ['มีรูป', 'ลบรูป']

    if changes:
        branch.save()
        if old_files:
            storage = Branch._meta.get_field('cover_image').storage
            # ลบไฟล์เก่าหลังบันทึกสำเร็จเท่านั้น ถ้า rollback รูปเดิมยังอยู่
            transaction.on_commit(lambda: [storage.delete(name) for name in old_files])
    return changes


def set_open(branch: Branch, *, is_open: bool) -> bool:
    if branch.is_open == is_open:
        return False
    branch.is_open = is_open
    branch.save(update_fields=['is_open', 'updated_at'])
    return True
