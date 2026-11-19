from django.conf import settings
from django.contrib.gis.geos import Point
from django.db import transaction

from ..models import Branch
from ..selectors import menu_selector
from ..selectors.menu_selector import CONSOLE_BRANCH_KEY, CUSTOMER_BRANCH_KEY, get_storefront_branch


class BranchError(Exception):
    """ข้อความแสดงให้เจ้าของเห็นได้"""


def get_or_create_main_branch() -> Branch:
    """เจ้าของเปิด Console ครั้งแรก ยังไม่มีร้าน -> สร้างร้านหลัก (ยังไม่มีพิกัด ยังไม่เปิดรับออเดอร์)"""
    branch = get_storefront_branch()
    if branch is None:
        with transaction.atomic():
            branch = get_storefront_branch() or Branch.objects.create(name=settings.SITE_NAME, is_open=False)
    return branch


def get_console_branch(session) -> Branch:
    """สาขาที่เจ้าของกำลังจัดการ ยังไม่มีร้านเลย -> สร้างร้านหลักให้"""
    return menu_selector.console_branch(session) or get_or_create_main_branch()


def switch_console_branch(session, branch: Branch) -> None:
    session[CONSOLE_BRANCH_KEY] = str(branch.pk)


def select_customer_branch(session, branch: Branch) -> bool:
    """
    ลูกค้าเลือกสาขา · คืน True ถ้าล้างตะกร้า (ของในตะกร้าเป็นของอีกสาขา ราคา/เมนูไม่ตรงกัน)
    """
    from apps.orders.services import cart_service

    cleared = False
    cart_branch = cart_service.branch_id(session)
    if cart_branch and cart_branch != str(branch.pk) and cart_service.count(session):
        cart_service.clear(session)
        cleared = True
    session[CUSTOMER_BRANCH_KEY] = str(branch.pk)
    return cleared


def create_branch(*, name: str, copy_rates_from: Branch | None = None) -> Branch:
    """สาขาใหม่: ปิดรับออเดอร์และซ่อนจากลูกค้าไว้ก่อน จนกว่าเจ้าของจะตั้งพิกัด/เมนูครบแล้วเปิดเอง"""
    name = (name or '').strip()
    if not name:
        raise BranchError('ใส่ชื่อสาขา')
    last = Branch.objects.order_by('-sort_order').values_list('sort_order', flat=True).first() or 0
    branch = Branch(name=name[:120], is_open=False, is_active=False, sort_order=last + 1)
    if copy_rates_from is not None:
        # ใช้อัตราค่าส่งเดียวกับสาขาหลักเป็นค่าเริ่มต้น แก้ทีหลังได้
        for field in ('delivery_base_km', 'delivery_base_fare', 'delivery_per_km_fare',
                      'rider_base_fare', 'rider_per_km_fare', 'max_delivery_km', 'opens_at', 'closes_at',
                      'kitchen_warn_minutes', 'kitchen_late_minutes'):
            setattr(branch, field, getattr(copy_rates_from, field))
    branch.save()
    return branch


def set_active(branch: Branch, *, active: bool) -> bool:
    """เปิด/ซ่อนสาขาจากลูกค้า · ซ่อนสาขาสุดท้ายไม่ได้ (ลูกค้าจะไม่มีร้านให้สั่ง)"""
    if branch.is_active == active:
        return False
    if not active and not Branch.objects.filter(is_active=True).exclude(pk=branch.pk).exists():
        raise BranchError('ต้องมีอย่างน้อย 1 สาขาที่เปิดใช้งาน')
    branch.is_active = active
    if not active:
        branch.is_open = False
    branch.save(update_fields=['is_active', 'is_open', 'updated_at'])
    return True


def _point_label(point):
    return f'{point.y:.6f},{point.x:.6f}' if point else None


TEXT_FIELDS = ('name', 'phone', 'address', 'maps_url')
VALUE_FIELDS = ('opens_at', 'closes_at', 'delivery_base_km', 'delivery_base_fare', 'delivery_per_km_fare',
                'rider_base_fare', 'rider_per_km_fare', 'max_delivery_km', 'kitchen_warn_minutes', 'kitchen_late_minutes')
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
