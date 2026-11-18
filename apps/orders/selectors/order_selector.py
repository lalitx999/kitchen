from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Prefetch, Q, QuerySet, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.accounts.models import CustomerAddress

from ..models import ACTIVE_STATUSES, Order, OrderItem, OrderStatus, OrderStatusLog

_LIST_FIELDS = ('id', 'order_number', 'status', 'total', 'created_at', 'branch_id', 'customer_id')


def _items_prefetch():
    return Prefetch('items', queryset=OrderItem.objects.only('id', 'order_id', 'name', 'quantity', 'line_total', 'options', 'unit_price', 'note'))


# --------------------------------------------------------------------------- ลูกค้า
def customer_orders(user) -> QuerySet[Order]:
    # กรองด้วยผู้ใช้ที่ล็อกอินเสมอ (ลูกค้าเห็นแค่ออเดอร์ตัวเอง)
    return (
        Order.objects.filter(customer=user)
        .only(*_LIST_FIELDS)
        .prefetch_related(_items_prefetch())
        .order_by('-created_at')
    )


def get_customer_order(user, order_id) -> Order:
    return get_object_or_404(
        Order.objects.select_related('branch', 'rider', 'rider__rider_profile', 'delivery_proof').prefetch_related(
            _items_prefetch(), 'delivery_proof__photos',
            Prefetch('status_logs', queryset=OrderStatusLog.objects.only('id', 'order_id', 'to_status', 'created_at')),
        ),
        pk=order_id, customer=user,
    )


def get_customer_order_status(user, order_id) -> Order:
    """ใช้กับ polling ทุกไม่กี่วินาที: ดึงแค่ field ที่ต้องใช้"""
    return get_object_or_404(Order.objects.only('id', 'status', 'customer_id', 'updated_at'), pk=order_id, customer=user)


def saved_addresses(user) -> QuerySet[CustomerAddress]:
    return user.addresses.only('id', 'label', 'address_text', 'note', 'location', 'last_used_at')[:5]


# --------------------------------------------------------------------------- console
def console_orders(*, status: str | None = None, query: str = '') -> QuerySet[Order]:
    qs = Order.objects.select_related('customer', 'branch').only(
        *_LIST_FIELDS, 'recipient_name', 'recipient_phone', 'customer__full_name', 'customer__email',
        'branch__id', 'branch__name',
    )
    if status == 'active':
        qs = qs.filter(status__in=ACTIVE_STATUSES)
    elif status in OrderStatus.values:
        qs = qs.filter(status=status)
    query = (query or '').strip()
    if query:
        qs = qs.filter(
            Q(order_number__icontains=query) | Q(recipient_phone__icontains=query)
            | Q(recipient_name__icontains=query) | Q(customer__email__icontains=query)
        )
    return qs.order_by('-created_at')


def get_console_order(order_id) -> Order:
    return get_object_or_404(
        Order.objects.select_related('customer', 'branch', 'rider', 'delivery_proof').prefetch_related(
            _items_prefetch(), 'slips', 'delivery_proof__photos',
            Prefetch('status_logs', queryset=OrderStatusLog.objects.select_related('actor').only(
                'id', 'order_id', 'from_status', 'to_status', 'note', 'created_at', 'actor__full_name')),
        ),
        pk=order_id,
    )


def status_counts() -> dict[str, int]:
    counts = {s: 0 for s in OrderStatus.values}
    for row in Order.objects.values('status').annotate(n=Count('id')):
        counts[row['status']] = row['n']
    counts['active'] = sum(counts[s] for s in ACTIVE_STATUSES)
    return counts


def today_summary() -> dict:
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    paid_today = Order.objects.filter(paid_at__gte=start, paid_at__lt=end).exclude(status=OrderStatus.CANCELLED)
    agg = paid_today.aggregate(revenue=Sum('total'), count=Count('id'))
    return {
        'revenue': agg['revenue'] or Decimal('0'),
        'paid_count': agg['count'],
        'created_count': Order.objects.filter(created_at__gte=start, created_at__lt=end).count(),
        'active_count': Order.objects.filter(status__in=ACTIVE_STATUSES).count(),
    }


def daily_sales(days: int = 7) -> list[dict]:
    """ยอดขายรายวัน (นับตามวันที่จ่ายเงิน ไม่รวมยกเลิก) คืนครบทุกวัน วันที่ไม่มียอดเป็น 0"""
    from django.db.models.functions import TruncDate

    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    rows = (
        Order.objects.filter(paid_at__date__gte=start).exclude(status=OrderStatus.CANCELLED)
        .annotate(day=TruncDate('paid_at', tzinfo=timezone.get_current_timezone()))
        .values('day').annotate(revenue=Sum('total'), count=Count('id'))
    )
    by_day = {row['day']: row for row in rows}
    result = []
    for i in range(days):
        day = start + timedelta(days=i)
        row = by_day.get(day, {})
        result.append({'day': day, 'revenue': row.get('revenue') or Decimal('0'), 'count': row.get('count') or 0})
    peak = max((r['revenue'] for r in result), default=Decimal('0'))
    for r in result:
        r['percent'] = int(r['revenue'] * 100 / peak) if peak else 0
    return result


def top_items(days: int = 30, limit: int = 5) -> list[dict]:
    since = timezone.now() - timedelta(days=days)
    return list(
        OrderItem.objects.filter(order__paid_at__gte=since).exclude(order__status=OrderStatus.CANCELLED)
        .values('name').annotate(qty=Sum('quantity'), revenue=Sum('line_total'))
        .order_by('-qty')[:limit]
    )


def export_rows(start, end):
    """ออเดอร์ตามช่วงวันที่สั่ง สำหรับไฟล์ CSV (iterator ไม่โหลดทั้งหมดเข้า memory)"""
    return (
        Order.objects.filter(created_at__date__gte=start, created_at__date__lte=end)
        .select_related('customer', 'rider')
        .only('order_number', 'created_at', 'paid_at', 'completed_at', 'status', 'subtotal', 'delivery_fee', 'total',
              'rider_fee', 'distance_km', 'recipient_name', 'recipient_phone', 'cancelled_reason',
              'customer__email', 'rider__full_name')
        .order_by('created_at')
        .iterator(chunk_size=500)
    )
