from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404

from apps.accounts.models import Role, User
from apps.orders.models import Order, OrderStatus

from ..models import RiderPayout

_UNPAID = Q(rider_orders__status=OrderStatus.COMPLETED, rider_orders__rider_payout__isnull=True)


def riders_with_unpaid() -> list[User]:
    """ไรเดอร์ทุกคน + จำนวนงาน/ยอดค้างจ่าย (query เดียว)"""
    riders = list(
        User.objects.filter(role=Role.RIDER)
        .annotate(unpaid_jobs=Count('rider_orders', filter=_UNPAID), unpaid_amount=Sum('rider_orders__rider_fee', filter=_UNPAID))
        .only('id', 'full_name', 'phone', 'is_active')
        .order_by('-is_active', 'full_name')
    )
    for rider in riders:
        rider.unpaid_amount = rider.unpaid_amount or Decimal('0')
    return riders


def get_rider(rider_id) -> User:
    return get_object_or_404(User.objects.select_related('rider_profile'), pk=rider_id, role=Role.RIDER)


def unpaid_orders(rider, limit=200):
    return list(
        Order.objects.filter(rider=rider, status=OrderStatus.COMPLETED, rider_payout__isnull=True)
        .only('id', 'order_number', 'completed_at', 'distance_km', 'rider_fee', 'delivery_fee')
        .order_by('-completed_at')[:limit]
    )


def unpaid_total(rider) -> Decimal:
    return Order.objects.filter(
        rider=rider, status=OrderStatus.COMPLETED, rider_payout__isnull=True,
    ).aggregate(t=Sum('rider_fee'))['t'] or Decimal('0')


def payout_history(rider, limit=30):
    return list(RiderPayout.objects.filter(rider=rider).select_related('paid_by').order_by('-created_at')[:limit])
