"""อ่านข้อมูลคูปอง (Console และหน้าชำระเงิน)"""
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from ..models import Coupon, OrderStatus


def console_coupons():
    """ทุกคูปอง + จำนวนครั้งที่ใช้ (ไม่นับออเดอร์ที่ยกเลิก) · 1 query"""
    return list(
        Coupon.objects.select_related('branch')
        .annotate(used=Count('orders', filter=~Q(orders__status=OrderStatus.CANCELLED)))
        .order_by('-is_active', '-created_at')
    )


def get_coupon(coupon_id) -> Coupon:
    return get_object_or_404(Coupon.objects.select_related('branch'), pk=coupon_id)


def checkout_coupons(branch):
    """คูปองที่แสดงให้ลูกค้าเลือกในหน้าชำระเงิน (ยังไม่หมดอายุ ใช้กับสาขานี้ได้) · ยังไม่ตรวจยอดขั้นต่ำ"""
    now = timezone.now()
    return list(
        Coupon.objects.filter(is_active=True, show_in_checkout=True)
        .filter(Q(branch__isnull=True) | Q(branch=branch))
        .filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
        .filter(Q(ends_at__isnull=True) | Q(ends_at__gt=now))
        .order_by('min_subtotal')[:10]
    )
