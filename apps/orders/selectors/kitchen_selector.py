"""ข้อมูลจอครัว: query คงที่ไม่ว่ามีกี่ออเดอร์ (จอนี้ถูกถามทุก 5 วินาที ต้องเบา)"""
from collections import Counter
from datetime import timedelta

from django.db.models import Prefetch
from django.utils import timezone

from ..models import Order, OrderItem, OrderStatus

KITCHEN_STATUSES = (OrderStatus.PAID, OrderStatus.PREPARING, OrderStatus.READY)
# ออเดอร์ที่ไรเดอร์รับไปแล้ว แสดงสั้นๆ อีก 30 นาที ให้ครัวรู้ว่าออกจากร้านแล้ว
RECENT_OUT_MINUTES = 30
# ค่าเริ่มต้นเมื่อสาขาไม่มีค่า (สาขาตั้งเองได้ใน Console > ข้อมูลร้าน)
DEFAULT_WARN_MINUTES, DEFAULT_LATE_MINUTES = 10, 15


def wait_thresholds(branch) -> tuple[int, int]:
    warn = getattr(branch, 'kitchen_warn_minutes', None) or DEFAULT_WARN_MINUTES
    late = getattr(branch, 'kitchen_late_minutes', None) or DEFAULT_LATE_MINUTES
    return warn, max(late, warn + 1)


def wait_level(minutes: int, warn: int, late: int) -> str:
    """สีหัวใบออเดอร์: ok (เขียว) / warn (ส้ม) / late (แดง)"""
    if minutes >= late:
        return 'late'
    return 'warn' if minutes >= warn else 'ok'


def to_cook_summary(orders) -> list[tuple[str, int]]:
    """"ต้องทำรวม": จำนวนของแต่ละเมนูในออเดอร์ที่ยังไม่เสร็จ (ใช้รายการอาหารที่ prefetch มาแล้ว ไม่ query เพิ่ม)"""
    counts = Counter()
    for order in orders:
        if order.status in (OrderStatus.PAID, OrderStatus.PREPARING):
            for item in order.items.all():
                counts[item.name] += item.quantity
    return counts.most_common()


def board(branch, now=None) -> dict:
    """ออเดอร์ของสาขาเดียว (แต่ละสาขามีจอครัวของตัวเอง)"""
    now = now or timezone.now()
    items = Prefetch('items', queryset=OrderItem.objects.only('id', 'order_id', 'name', 'quantity', 'options', 'note'))
    orders = list(
        Order.objects.filter(branch=branch, status__in=KITCHEN_STATUSES)
        .select_related('rider')
        .only('id', 'order_number', 'status', 'note', 'paid_at', 'updated_at', 'recipient_name', 'total', 'branch_id',
              'rider_arrived_at', 'rider__id', 'rider__full_name')
        .prefetch_related(items)
        .order_by('paid_at', 'created_at')   # จ่ายก่อนทำก่อน
    )
    out = list(
        Order.objects.filter(branch=branch, status=OrderStatus.DELIVERING,
                             updated_at__gte=now - timedelta(minutes=RECENT_OUT_MINUTES))
        .only('id', 'order_number', 'updated_at')
        .order_by('-updated_at')[:10]
    )
    warn, late = wait_thresholds(branch)
    for order in orders:
        start = order.paid_at or order.updated_at
        order.wait_since = start   # จอครัวนับวินาทีต่อเองในเบราว์เซอร์ (kitchen.js) ไม่ต้องถามเซิร์ฟเวอร์ทุกวินาที
        order.waiting_minutes = max(0, int((now - start).total_seconds() // 60))
        # อาหารพร้อมแล้ว = ครัวทำเสร็จ ไม่ต้องเร่ง ไม่ขึ้นสีส้ม/แดง
        order.wait_level = 'ok' if order.status == OrderStatus.READY else wait_level(order.waiting_minutes, warn, late)
        order.is_late = order.wait_level == 'late'
    columns = {status: [o for o in orders if o.status == status] for status in KITCHEN_STATUSES}
    return {
        'new_orders': columns[OrderStatus.PAID],
        'preparing_orders': columns[OrderStatus.PREPARING],
        'ready_orders': columns[OrderStatus.READY],
        'out_orders': out,
        # id ของออเดอร์ใหม่ ให้ JS เทียบว่ามีออเดอร์เพิ่มไหม แล้วเล่นเสียง
        'new_order_ids': [str(o.pk) for o in columns[OrderStatus.PAID]],
        # มุมมอง "จอครัว": ทุกใบเรียงตามเวลาจ่าย (ใครจ่ายก่อนอยู่ซ้ายบน)
        'active_orders': orders,
        'to_cook': to_cook_summary(orders),
        'warn_minutes': warn, 'late_minutes': late,
    }


def get_kitchen_order(order_id, branch) -> Order | None:
    return Order.objects.filter(pk=order_id, branch=branch).only('id', 'order_number', 'status', 'branch_id').first()


HISTORY_LIMIT = 100


def today_history(branch) -> list[Order]:
    """ประวัติวันนี้ของสาขา: ออเดอร์ที่จ่ายแล้ววันนี้และออกจากครัวแล้ว (กำลังส่ง/ส่งแล้ว/ยกเลิก) — 1 query"""
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    return list(
        Order.objects.filter(
            branch=branch, paid_at__gte=start,
            status__in=(OrderStatus.DELIVERING, OrderStatus.COMPLETED, OrderStatus.CANCELLED),
        )
        .select_related('rider')
        .only('id', 'order_number', 'status', 'paid_at', 'picked_up_at', 'completed_at', 'cancelled_at',
              'cancelled_reason', 'total', 'branch_id', 'rider__id', 'rider__full_name')
        .order_by('-paid_at')[:HISTORY_LIMIT]
    )
