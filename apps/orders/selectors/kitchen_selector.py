"""ข้อมูลจอครัว: query คงที่ไม่ว่ามีกี่ออเดอร์ (จอนี้ถูกถามทุก 5 วินาที ต้องเบา)"""
from datetime import timedelta

from django.db.models import Prefetch
from django.utils import timezone

from ..models import Order, OrderItem, OrderStatus

KITCHEN_STATUSES = (OrderStatus.PAID, OrderStatus.PREPARING, OrderStatus.READY)
# ออเดอร์ที่ไรเดอร์รับไปแล้ว แสดงสั้นๆ อีก 30 นาที ให้ครัวรู้ว่าออกจากร้านแล้ว
RECENT_OUT_MINUTES = 30
LATE_AFTER_MINUTES = 15


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
    for order in orders:
        start = order.paid_at or order.updated_at
        order.waiting_minutes = max(0, int((now - start).total_seconds() // 60))
        order.is_late = order.status != OrderStatus.READY and order.waiting_minutes >= LATE_AFTER_MINUTES
    columns = {status: [o for o in orders if o.status == status] for status in KITCHEN_STATUSES}
    return {
        'new_orders': columns[OrderStatus.PAID],
        'preparing_orders': columns[OrderStatus.PREPARING],
        'ready_orders': columns[OrderStatus.READY],
        'out_orders': out,
        # id ของออเดอร์ใหม่ ให้ JS เทียบว่ามีออเดอร์เพิ่มไหม แล้วเล่นเสียง
        'new_order_ids': [str(o.pk) for o in columns[OrderStatus.PAID]],
    }


def get_kitchen_order(order_id, branch) -> Order | None:
    return Order.objects.filter(pk=order_id, branch=branch).only('id', 'order_number', 'status', 'branch_id').first()
