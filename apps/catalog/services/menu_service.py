"""เพิ่ม/แก้/ลบ เมนู หมวด ตัวเลือก — คืน dict การเปลี่ยนแปลงให้ console บันทึก AuditLog"""
from decimal import Decimal

from django.db import IntegrityError, transaction

from ..models import Branch, Category, MenuItem, MenuOption

ITEM_FIELDS = ('name', 'description', 'price', 'category', 'is_available', 'sort_order')


class DuplicateCategory(Exception):
    pass


def create_item(branch: Branch, *, image=None, **data) -> MenuItem:
    item = MenuItem(branch=branch, **{k: data[k] for k in ITEM_FIELDS if k in data})
    with transaction.atomic():
        item.save()  # ต้องมี id ก่อน เพราะชื่อไฟล์รูปใช้ id
        if image:
            item.image = image
            item.save(update_fields=['image'])
    return item


def update_item(item: MenuItem, *, image=None, remove_image=False, **data) -> dict:
    changes = {}
    for field in ITEM_FIELDS:
        if field not in data:
            continue
        old, new = getattr(item, field), data[field]
        if old != new:
            changes[field] = [str(old) if old is not None else None, str(new) if new is not None else None]
            setattr(item, field, new)
    if remove_image and item.image:
        item.image.delete(save=False)
        item.image = ''
        changes['image'] = ['มีรูป', 'ลบรูป']
    elif image:
        if item.image:
            item.image.delete(save=False)
        item.image = image
        changes['image'] = ['', 'อัปโหลดรูปใหม่']
    if changes:
        item.save()
    return changes


def set_available(item: MenuItem, *, available: bool) -> bool:
    if item.is_available == available:
        return False
    item.is_available = available
    item.save(update_fields=['is_available', 'updated_at'])
    return True


def delete_item(item: MenuItem) -> None:
    # ออเดอร์เก่าเก็บชื่อ/ราคาไว้ใน OrderItem แล้ว ลบเมนูได้โดยประวัติไม่หาย
    if item.image:
        item.image.delete(save=False)
    item.delete()


def create_category(branch: Branch, *, name: str, sort_order: int = 0) -> Category:
    try:
        with transaction.atomic():
            return Category.objects.create(branch=branch, name=name.strip(), sort_order=sort_order)
    except IntegrityError as exc:
        raise DuplicateCategory from exc


def update_category(category: Category, *, name: str, sort_order: int) -> dict:
    changes = {}
    if category.name != name.strip():
        changes['name'] = [category.name, name.strip()]
        category.name = name.strip()
    if category.sort_order != sort_order:
        changes['sort_order'] = [category.sort_order, sort_order]
        category.sort_order = sort_order
    if changes:
        try:
            with transaction.atomic():
                category.save()
        except IntegrityError as exc:
            raise DuplicateCategory from exc
    return changes


def delete_category(category: Category) -> int:
    """เมนูในหมวดไม่ถูกลบ แค่ย้ายไป "ไม่มีหมวด" (FK SET_NULL) คืนจำนวนเมนูที่ถูกย้าย"""
    moved = category.items.count()
    category.delete()
    return moved


def add_option(item: MenuItem, *, name: str, extra_price: Decimal) -> MenuOption:
    next_order = item.options.count()
    return MenuOption.objects.create(menu_item=item, name=name.strip(), extra_price=extra_price, sort_order=next_order)


def delete_option(item: MenuItem, option_id) -> MenuOption | None:
    option = item.options.filter(pk=option_id).first()
    if option:
        option.delete()
    return option
