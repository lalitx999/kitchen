from dataclasses import dataclass
from datetime import datetime, time

from django.core.exceptions import ValidationError
from django.db.models import Prefetch, QuerySet
from django.shortcuts import get_object_or_404
from django.utils import timezone

from ..models import Branch, Category, MenuItem, MenuOption, MenuOptionGroup


CUSTOMER_BRANCH_KEY = 'branch_id'        # สาขาที่ลูกค้าเลือก (session)
CONSOLE_BRANCH_KEY = 'console_branch_id'  # สาขาที่เจ้าของกำลังจัดการใน Console/จอครัว (session)


def get_storefront_branch() -> Branch | None:
    """สาขาหลัก: สาขาแรกที่เปิดใช้งาน (ใช้เป็นค่าเริ่มต้นเมื่อยังไม่ได้เลือก)"""
    return Branch.objects.filter(is_active=True).order_by('sort_order', 'created_at').first()


def active_branches() -> list[Branch]:
    """สาขาที่ลูกค้าเห็น (หน้าเลือกสาขา) · ไม่ดึงรูป/อัตราค่าส่งที่ไม่ใช้ในรายการ"""
    return list(Branch.objects.filter(is_active=True).order_by('sort_order', 'created_at'))


def all_branches() -> list[Branch]:
    """ทุกสาขารวมที่ปิดใช้งาน (หน้าจัดการสาขาของเจ้าของ)"""
    return list(Branch.objects.order_by('sort_order', 'created_at'))


def get_branch(branch_id, *, active_only: bool = True) -> Branch | None:
    qs = Branch.objects.filter(is_active=True) if active_only else Branch.objects.all()
    try:
        return qs.filter(pk=branch_id).first() if branch_id else None
    except (ValidationError, ValueError, TypeError):  # id ใน session เสีย/ไม่ใช่ UUID
        return None


def customer_branch(session, branches: list[Branch] | None = None) -> Branch | None:
    """
    สาขาที่ลูกค้ากำลังสั่ง: มีสาขาเดียว = สาขานั้นเลย · หลายสาขา = ที่เลือกไว้ใน session
    ยังไม่เลือก/สาขาที่เลือกถูกปิด -> None (หน้าแรกแสดงรายการให้เลือก)
    ส่ง branches (active_branches()) มาด้วยได้ เพื่อไม่ query ซ้ำ
    """
    if branches is None:
        branches = active_branches()
    selected = str(session.get(CUSTOMER_BRANCH_KEY) or '')
    for branch in branches:
        if str(branch.pk) == selected:
            return branch
    return branches[0] if len(branches) == 1 else None


def console_branch(session, branches: list[Branch] | None = None) -> Branch | None:
    """
    สาขาที่เจ้าของกำลังจัดการ (รวมสาขาที่ปิดใช้งาน เพื่อแก้ไขก่อนเปิด) · ไม่ได้เลือก = สาขาหลัก
    ส่ง branches (all_branches()) มาด้วยได้ เพื่อไม่ query ซ้ำ
    """
    if branches is None:
        return get_branch(session.get(CONSOLE_BRANCH_KEY), active_only=False) or get_storefront_branch()
    selected = str(session.get(CONSOLE_BRANCH_KEY) or '')
    for branch in branches:
        if str(branch.pk) == selected:
            return branch
    return next((b for b in branches if b.is_active), branches[0] if branches else None)


def kitchen_branch(user, session) -> Branch | None:
    """จอครัว: เจ้าของใช้สาขาที่เลือกใน Console · พนักงานครัวใช้สาขาของตัวเอง (ไม่ได้ตั้ง = สาขาหลัก)"""
    if user.is_owner:
        return console_branch(session)
    if user.branch_id:
        return get_branch(user.branch_id, active_only=False)
    return get_storefront_branch()


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
    if not branch.is_active:
        # สาขาที่ซ่อนจากลูกค้า สั่งไม่ได้แม้สวิตช์เปิดรับออเดอร์จะเปิดค้างไว้
        return ShopStatus(False, 'สาขานี้ยังไม่เปิดให้ลูกค้าสั่ง')
    if branch.location is None:
        return ShopStatus(False, 'ร้านยังไม่ได้ตั้งพิกัด จึงยังคิดค่าส่งไม่ได้')
    if not branch.is_open:
        return ShopStatus(False, 'ร้านปิดรับออเดอร์ชั่วคราว')
    now = timezone.localtime(at or timezone.now()).time()
    if not _within_hours(branch.opens_at, branch.closes_at, now):
        return ShopStatus(False, f'นอกเวลาเปิด ({branch.opens_at:%H:%M}-{branch.closes_at:%H:%M} น.)')
    return ShopStatus(True)


def _options_prefetch():
    return Prefetch('options', queryset=MenuOption.objects.only(
        'id', 'menu_item_id', 'group_id', 'name', 'extra_price', 'sort_order'))


def _groups_prefetch():
    return Prefetch('option_groups', queryset=MenuOptionGroup.objects.only(
        'id', 'menu_item_id', 'name', 'min_select', 'max_select', 'sort_order'))


def storefront_menu(branch: Branch) -> tuple[list[Category], list[MenuItem]]:
    """
    คืน (หมวดที่มีเมนูขาย พร้อม items, เมนูที่ไม่มีหมวด)
    ใช้ 3 query คงที่ ไม่ว่าเมนูจะมีกี่รายการ
    """
    item_qs = (
        MenuItem.objects.filter(branch=branch, is_available=True)
        .only('id', 'branch_id', 'category_id', 'name', 'description', 'price', 'image', 'sort_order')
        .prefetch_related(_options_prefetch(), _groups_prefetch())
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
        .prefetch_related(_options_prefetch(), _groups_prefetch())
    )
    categories = list(Category.objects.filter(branch=branch))
    by_category: dict = {}
    for item in items:
        by_category.setdefault(item.category_id, []).append(item)
    for category in categories:
        category.menu = by_category.get(category.id, [])
    return categories, by_category.get(None, [])


def get_branch_item(branch: Branch, item_id) -> MenuItem:
    return get_object_or_404(MenuItem.objects.prefetch_related(_options_prefetch(), _groups_prefetch()),
                             pk=item_id, branch=branch)


def get_branch_category(branch: Branch, category_id) -> Category:
    return get_object_or_404(Category, pk=category_id, branch=branch)


def items_for_pricing(branch: Branch, item_ids) -> dict:
    """ราคาล่าสุดจากฐานข้อมูล ใช้คิดเงินตอนตะกร้า/สั่ง (ไม่เชื่อราคาจากเบราว์เซอร์)"""
    qs: QuerySet[MenuItem] = (
        MenuItem.objects.filter(branch=branch, pk__in=list(item_ids))
        .only('id', 'name', 'price', 'is_available', 'image', 'branch_id')
        .prefetch_related(_options_prefetch(), _groups_prefetch())
    )
    return {str(item.pk): item for item in qs}


def category_choices(branch: Branch) -> QuerySet[Category]:
    return Category.objects.filter(branch=branch).only('id', 'name')


def suggestion_items(branch: Branch, *, exclude_ids, popular_ids=(), limit: int = 8) -> list[MenuItem]:
    """
    "รายการอื่นที่คนมักสั่งด้วย" ในหน้าตะกร้า: เมนูขายดี (popular_ids จาก orders) ก่อน แล้วเติมด้วยเมนูอื่น
    ไม่เอาเมนูที่อยู่ในตะกร้าแล้ว · 1 query
    """
    exclude = {str(i) for i in exclude_ids}
    items = [i for i in MenuItem.objects.filter(branch=branch, is_available=True)
             .only('id', 'name', 'price', 'image', 'sort_order').prefetch_related(_options_prefetch())
             if str(i.pk) not in exclude]
    rank = {str(pk): n for n, pk in enumerate(popular_ids)}
    items.sort(key=lambda i: (rank.get(str(i.pk), len(rank)), i.sort_order, i.name))
    return items[:limit]
