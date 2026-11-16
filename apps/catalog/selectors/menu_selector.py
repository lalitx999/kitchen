from dataclasses import dataclass
from datetime import datetime, time

from django.db.models import Prefetch, QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone

from ..models import Branch, Category, MenuItem, MenuOption


def get_storefront_branch() -> Branch | None:
    """ร้านเดียวตอนนี้: สาขาแรกที่ใช้งานอยู่ (เพิ่มสาขาแล้วค่อยให้ลูกค้าเลือก)"""
    return Branch.objects.filter(is_active=True).order_by('sort_order', 'created_at').first()


@dataclass(frozen=True)
class ShopStatus:
    accepting: bool
    reason: str = ''


def _within_hours(opens_at: time | None, closes_at: time | None, now: time) -> bool:
    if opens_at is None or closes_at is None:
        return True  # ไม่ได้ตั้งเวลา = ใช้สวิตช์เปิด/ปิดอย่างเดียว
    if opens_at <= closes_at:
        return opens_at <= now < closes_at
    return now >= opens_at or now < closes_at  # เปิดข้ามเที่ยงคืน เช่น 17:00-02:00


def shop_status(branch: Branch | None, at: datetime | None = None) -> ShopStatus:
    if branch is None:
        return ShopStatus(False, 'ร้านยังไม่ได้ตั้งค่า')
    if branch.location is None:
        return ShopStatus(False, 'ร้านยังไม่ได้ตั้งพิกัด จึงยังคิดค่าส่งไม่ได้')
    if not branch.is_open:
        return ShopStatus(False, 'ร้านปิดรับออเดอร์ชั่วคราว')
    now = timezone.localtime(at or timezone.now()).time()
    if not _within_hours(branch.opens_at, branch.closes_at, now):
        return ShopStatus(False, f'นอกเวลาเปิด ({branch.opens_at:%H:%M}-{branch.closes_at:%H:%M} น.)')
    return ShopStatus(True)


def _options_prefetch():
    return Prefetch('options', queryset=MenuOption.objects.only('id', 'menu_item_id', 'name', 'extra_price', 'sort_order'))


def storefront_menu(branch: Branch) -> tuple[list[Category], list[MenuItem]]:
    """
    คืน (หมวดที่มีเมนูขาย พร้อม items, เมนูที่ไม่มีหมวด)
    ใช้ 3 query คงที่ ไม่ว่าเมนูจะมีกี่รายการ
    """
    item_qs = (
        MenuItem.objects.filter(branch=branch, is_available=True)
        .only('id', 'branch_id', 'category_id', 'name', 'description', 'price', 'image', 'sort_order')
        .prefetch_related(_options_prefetch())
    )
    items = list(item_qs)
    categories = list(Category.objects.filter(branch=branch).only('id', 'name', 'sort_order'))
    by_category: dict = {}
    for item in items:
        by_category.setdefault(item.category_id, []).append(item)
    for category in categories:
        category.menu = by_category.get(category.id, [])
    return [c for c in categories if c.menu], by_category.get(None, [])


def console_menu(branch: Branch) -> tuple[list[Category], list[MenuItem]]:
    """เหมือน storefront แต่รวมเมนูที่ปิดขาย และหมวดที่ยังว่าง"""
    items = list(
        MenuItem.objects.filter(branch=branch)
        .select_related('category')
        .prefetch_related(_options_prefetch())
    )
    categories = list(Category.objects.filter(branch=branch))
    by_category: dict = {}
    for item in items:
        by_category.setdefault(item.category_id, []).append(item)
    for category in categories:
        category.menu = by_category.get(category.id, [])
    return categories, by_category.get(None, [])


def get_branch_item(branch: Branch, item_id) -> MenuItem:
    return get_object_or_404(MenuItem.objects.prefetch_related(_options_prefetch()), pk=item_id, branch=branch)


def get_branch_category(branch: Branch, category_id) -> Category:
    return get_object_or_404(Category, pk=category_id, branch=branch)


def items_for_pricing(branch: Branch, item_ids) -> dict:
    """ราคาล่าสุดจากฐานข้อมูล ใช้คิดเงินตอนตะกร้า/สั่ง (ไม่เชื่อราคาจากเบราว์เซอร์)"""
    qs: QuerySet[MenuItem] = (
        MenuItem.objects.filter(branch=branch, pk__in=list(item_ids))
        .only('id', 'name', 'price', 'is_available', 'image', 'branch_id')
        .prefetch_related(_options_prefetch())
    )
    return {str(item.pk): item for item in qs}


def category_choices(branch: Branch) -> QuerySet[Category]:
    return Category.objects.filter(branch=branch).only('id', 'name')
