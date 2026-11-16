from django.db.models import QuerySet
from django.http import Http404

from apps.accounts.models import Role

from ..models import SlipStatus, SlipTransaction
from ..services.slip_service import REVIEWABLE


def latest_slip(order) -> SlipTransaction | None:
    return order.slips.only('id', 'order_id', 'status', 'reason', 'attempt_no', 'created_at').order_by('-attempt_no').first()


def review_queue() -> QuerySet[SlipTransaction]:
    return (
        SlipTransaction.objects.filter(status__in=REVIEWABLE)
        .select_related('order', 'order__customer')
        .order_by('created_at')
    )


def recent_reviewed(limit: int = 20) -> QuerySet[SlipTransaction]:
    return (
        SlipTransaction.objects.filter(status__in=(SlipStatus.APPROVED, SlipStatus.REJECTED))
        .select_related('order', 'reviewed_by')
        .order_by('-reviewed_at')[:limit]
    )


def pending_review_count() -> int:
    return SlipTransaction.objects.filter(status=SlipStatus.NEEDS_REVIEW).count()


def get_reviewable(slip_id) -> SlipTransaction:
    slip = SlipTransaction.objects.select_related('order').filter(pk=slip_id).first()
    if slip is None:
        raise Http404
    return slip


def get_slip_for_viewer(user, slip_id) -> SlipTransaction:
    """รูปสลิป: เจ้าของร้านดูได้ทุกใบ ลูกค้าดูได้เฉพาะของออเดอร์ตัวเอง นอกนั้น 404 (ไม่บอกว่ามีอยู่)"""
    slip = SlipTransaction.objects.select_related('order').filter(pk=slip_id).first()
    if slip is None or not user.is_authenticated:
        raise Http404
    if user.role == Role.OWNER or slip.order.customer_id == user.pk:
        return slip
    raise Http404


def payment_context(order) -> dict:
    """ข้อมูลกล่องชำระเงินในหน้าออเดอร์ลูกค้า"""
    from django.conf import settings

    from apps.orders.models import OrderStatus

    from ..services import promptpay_service, slip_service

    context = {'latest_slip': latest_slip(order)}
    if order.status == OrderStatus.PENDING_PAYMENT:
        try:
            context['qr_data_uri'] = promptpay_service.qr_data_uri(order.total)
        except promptpay_service.PromptPayNotConfigured as exc:
            context['qr_error'] = str(exc)
        context.update({
            'promptpay_masked': promptpay_service.masked_promptpay_id(),
            'account_name': settings.SHOP_ACCOUNT_NAMES[0] if settings.SHOP_ACCOUNT_NAMES else '',
            'deadline': slip_service.payment_deadline(order),
            'remaining_attempts': slip_service.remaining_attempts(order),
            'max_mb': settings.SLIP_MAX_BYTES // (1024 * 1024),
        })
    return context
