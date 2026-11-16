from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Prefetch, Sum
from django.utils import timezone

from apps.orders.models import Order, OrderItem, OrderStatus
from apps.orders.services.order_service import ASSIGNABLE_STATUSES

from ..services import live_location_service

ACTIVE_JOB_STATUSES = (*ASSIGNABLE_STATUSES, OrderStatus.DELIVERING)
_FIELDS = (
    'id', 'order_number', 'status', 'rider_id', 'branch_id', 'paid_at', 'rider_fee', 'distance_km', 'total',
    'recipient_name', 'recipient_phone', 'address_text', 'address_note', 'delivery_location', 'note',
    'branch__name', 'branch__phone', 'branch__address', 'branch__location',
)


def _items():
    return Prefetch('items', queryset=OrderItem.objects.only('id', 'order_id', 'name', 'quantity', 'options', 'note'))


def available_jobs():
    """งานที่ยังไม่มีไรเดอร์รับ (จ่ายเงินแล้วเท่านั้น) — query คงที่"""
    return list(
        Order.objects.filter(status__in=ASSIGNABLE_STATUSES, rider__isnull=True)
        .select_related('branch').only(*_FIELDS).prefetch_related(_items())
        .order_by('paid_at')
    )


def my_jobs(rider):
    # กรองด้วยไรเดอร์ที่ล็อกอินเสมอ (ไรเดอร์เห็นแค่งานตัวเอง)
    return list(
        Order.objects.filter(rider=rider, status__in=ACTIVE_JOB_STATUSES)
        .select_related('branch').only(*_FIELDS).prefetch_related(_items())
        .order_by('rider_assigned_at')
    )


def has_active_jobs(rider) -> bool:
    return Order.objects.filter(rider=rider, status__in=ACTIVE_JOB_STATUSES).exists()


def get_job(order_id):
    return Order.objects.filter(pk=order_id).select_related('branch').first()


def today_summary(rider) -> dict:
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    agg = Order.objects.filter(
        rider=rider, status=OrderStatus.COMPLETED, completed_at__gte=start, completed_at__lt=start + timedelta(days=1),
    ).aggregate(n=Count('id'), earned=Sum('rider_fee'))
    return {'jobs': agg['n'], 'earned': agg['earned'] or Decimal('0')}


def tracking_for_order(order) -> dict:
    """ข้อมูลติดตามสำหรับลูกค้า: มีเฉพาะตอนกำลังไปส่ง · พิกัดเก่าบอกตรงๆ ไม่แต่งตำแหน่ง"""
    if order.status != OrderStatus.DELIVERING or not order.rider_id:
        return {'available': False}
    location = live_location_service.get(order.rider_id)
    if location is None:
        return {'available': True, 'has_location': False}
    meters = live_location_service.haversine_m(
        location.lat, location.lng, order.delivery_location.y, order.delivery_location.x,
    )
    return {
        'available': True, 'has_location': True,
        'lat': location.lat, 'lng': location.lng, 'heading': location.heading,
        'age_seconds': location.age_seconds(), 'is_stale': location.is_stale(),
        'distance_m': int(meters), 'distance_km': round(meters / 1000, 1),
        'near': meters < 500,
    }


def get_proof_for_viewer(user, order_id):
    """รูปหลักฐานการส่ง: เจ้าของร้าน, ลูกค้าเจ้าของออเดอร์, ไรเดอร์คนส่ง · คนอื่นได้ None (view ตอบ 404)"""
    from apps.accounts.models import Role

    from ..models import DeliveryProof

    proof = DeliveryProof.objects.select_related('order').filter(order_id=order_id).first()
    if proof is None or not user.is_authenticated:
        return None
    if user.role == Role.OWNER or proof.order.customer_id == user.pk or proof.rider_id == user.pk:
        return proof
    return None
