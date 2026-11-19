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
    'rider_assigned_at', 'rider_arrived_at', 'picked_up_at', 'completed_at',
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


def _day_start(days_ago: int = 0):
    return timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_ago)


def _completed_summary(rider, since) -> dict:
    agg = Order.objects.filter(rider=rider, status=OrderStatus.COMPLETED, completed_at__gte=since).aggregate(
        n=Count('id'), earned=Sum('rider_fee'), km=Sum('distance_km'),
    )
    return {'jobs': agg['n'], 'earned': agg['earned'] or Decimal('0'), 'km': agg['km'] or Decimal('0')}


def today_summary(rider) -> dict:
    """ส่งสำเร็จวันนี้: จำนวนเที่ยว, ค่าส่ง, กม. (ระยะร้าน-ลูกค้าตามที่คิดค่าส่ง) — 1 query"""
    return _completed_summary(rider, _day_start())


def week_summary(rider) -> dict:
    """7 วันล่าสุด (รวมวันนี้)"""
    return _completed_summary(rider, _day_start(6))


# แท็บหน้า "งาน" ของไรเดอร์: ชื่อแท็บ -> สถานะที่แสดง (None = ทุกสถานะ)
HISTORY_TABS = {
    'all': None,
    'active': ACTIVE_JOB_STATUSES,
    'done': (OrderStatus.COMPLETED,),
    'cancelled': (OrderStatus.CANCELLED,),
}
HISTORY_DAYS = 60
HISTORY_LIMIT = 50


def history(rider, tab: str = 'all') -> list[Order]:
    """
    งานของไรเดอร์คนนี้ 60 วันล่าสุด (สูงสุด 50 รายการ) — 1 query ไม่ดึงรายการอาหาร
    ยกเลิก = งานที่ไรเดอร์คนนี้ถืออยู่ตอนออเดอร์ถูกยกเลิก
    """
    statuses = HISTORY_TABS.get(tab, None)
    qs = Order.objects.filter(rider=rider, rider_assigned_at__gte=_day_start(HISTORY_DAYS))
    if statuses:
        qs = qs.filter(status__in=statuses)
    return list(
        qs.select_related('branch')
        .only('id', 'order_number', 'status', 'rider_id', 'branch_id', 'branch__name', 'address_text', 'rider_fee',
              'distance_km', 'rider_assigned_at', 'completed_at', 'cancelled_at', 'cancelled_reason')
        .order_by('-rider_assigned_at')[:HISTORY_LIMIT]
    )


def get_my_job(rider, order_id) -> Order | None:
    """งาน 1 งานของไรเดอร์คนนี้ (ทุกสถานะ) พร้อมร้านและรายการอาหาร · งานคนอื่น = None (view ตอบ 404)"""
    return (
        Order.objects.filter(pk=order_id, rider=rider)
        .select_related('branch').only(*_FIELDS).prefetch_related(_items())
        .first()
    )


def proof_photo_count(order) -> int:
    from ..models import DeliveryProofPhoto

    return DeliveryProofPhoto.objects.filter(proof__order=order).count()


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


def _can_view_proof(user, proof) -> bool:
    from apps.accounts.models import Role

    return user.is_authenticated and (
        user.role == Role.OWNER or proof.order.customer_id == user.pk or proof.rider_id == user.pk
    )


def get_proof_photo_for_viewer(user, order_id, index: int = 0):
    """
    รูปหลักฐานการส่ง (รูปที่ index): เจ้าของร้าน, ลูกค้าเจ้าของออเดอร์, ไรเดอร์คนส่ง
    คนอื่น/ไม่มีรูป ได้ None (view ตอบ 404 ไม่บอกว่ามีออเดอร์นี้อยู่)
    """
    from ..models import DeliveryProofPhoto

    photo = (
        DeliveryProofPhoto.objects.select_related('proof__order')
        .filter(proof__order_id=order_id).order_by('sort_order', 'created_at')[index:index + 1].first()
    )
    if photo is None or not _can_view_proof(user, photo.proof):
        return None
    return photo
