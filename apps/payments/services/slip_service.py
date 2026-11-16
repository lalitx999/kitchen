"""
ขั้นตอนชำระเงิน
  ลูกค้าแนบสลิป -> submit_slip()  (ออเดอร์: รอชำระ -> รอตรวจสลิป)
  Celery -> verify_slip()          (ผ่าน -> ชำระแล้ว / ไม่ผ่าน -> กลับไปรอชำระ / EasySlip ใช้ไม่ได้ -> รอเจ้าของตรวจ)
  เจ้าของ -> approve_manually() / reject_manually()
  Celery beat -> expire_unpaid_orders()  (ไม่จ่ายเกินเวลา -> ยกเลิก)
"""
import hashlib
import logging
from datetime import timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.core import images
from apps.orders.models import Order, OrderStatus
from apps.orders.services import order_service

from ..models import ReviewSource, SlipStatus, SlipTransaction
from . import easyslip_client, slip_checks

logger = logging.getLogger(__name__)

CONTENT_TYPES = images.CONTENT_TYPES


class SlipError(Exception):
    """ข้อความแสดงให้ลูกค้า/เจ้าของเห็นได้"""


# --------------------------------------------------------------------------- ลูกค้าแนบสลิป
def _read_image(uploaded) -> tuple[bytes, str]:
    try:
        return images.read_uploaded_image(uploaded, max_bytes=settings.SLIP_MAX_BYTES)
    except images.InvalidImage as exc:
        raise SlipError(str(exc)) from exc


def remaining_attempts(order: Order) -> int:
    return max(0, settings.SLIP_MAX_ATTEMPTS - order.slips.count())


def submit_slip(order: Order, customer, uploaded) -> SlipTransaction:
    if order.customer_id != customer.pk:
        raise SlipError('ไม่พบออเดอร์')
    if order.status != OrderStatus.PENDING_PAYMENT:
        raise SlipError('ออเดอร์นี้ไม่ได้อยู่ในขั้นรอชำระเงิน')
    attempts = order.slips.count()
    if attempts >= settings.SLIP_MAX_ATTEMPTS:
        raise SlipError('แนบสลิปครบจำนวนครั้งแล้ว กรุณาโทรหาร้าน')

    data, ext = _read_image(uploaded)
    digest = hashlib.sha256(data).hexdigest()
    # รูปไฟล์เดียวกันกับสลิปที่เคยอนุมัติแล้ว = เอาสลิปเก่ามาใช้ซ้ำ ปฏิเสธทันทีไม่ต้องเสียโควต้า EasySlip
    if SlipTransaction.objects.filter(image_sha256=digest, status=SlipStatus.APPROVED).exists():
        raise SlipError('สลิปนี้ถูกใช้ไปแล้ว')

    manual = settings.PAYMENT_VERIFICATION_MODE == 'MANUAL'
    uploaded.seek(0)
    try:
        with transaction.atomic():
            slip = SlipTransaction(
                order=order, attempt_no=attempts + 1, image_sha256=digest,
                status=SlipStatus.NEEDS_REVIEW if manual else SlipStatus.PROCESSING,
                reason='รอเจ้าของร้านตรวจ' if manual else '',
            )
            slip.image.save(f'slip.{ext}', uploaded, save=False)
            slip.save()
            # lock ออเดอร์และเปลี่ยนสถานะ: ถ้าแนบซ้ำพร้อมกัน 2 ครั้ง ครั้งที่สองจะเปลี่ยนสถานะไม่ได้และถูก rollback
            order_service.transition_order(order, OrderStatus.PAYMENT_REVIEW, actor=customer, note=f'แนบสลิปครั้งที่ {slip.attempt_no}')
            if not manual:
                from ..tasks import verify_slip_task
                transaction.on_commit(lambda: verify_slip_task.delay(str(slip.pk)))
            else:
                _notify_owner_review(order.pk)
    except (order_service.InvalidTransition, IntegrityError) as exc:
        raise SlipError('กำลังตรวจสลิปก่อนหน้าอยู่ รอสักครู่') from exc
    return slip


def _notify_owner_review(order_id) -> None:
    from apps.notifications.services import order_events
    transaction.on_commit(lambda: order_events.slip_needs_review(order_id))


# --------------------------------------------------------------------------- ตรวจอัตโนมัติ (Celery)
def _trans_ref_used(trans_ref: str) -> bool:
    return SlipTransaction.objects.filter(trans_ref=trans_ref, status=SlipStatus.APPROVED).exists()


def verify_slip(slip_id) -> str:
    """idempotent: รันซ้ำได้ ถ้าสลิปไม่ได้อยู่ในสถานะกำลังตรวจแล้วจะไม่ทำอะไร คืนสถานะสุดท้าย"""
    slip = SlipTransaction.objects.select_related('order').filter(pk=slip_id).first()
    if slip is None or slip.status != SlipStatus.PROCESSING:
        return slip.status if slip else 'MISSING'

    # เรียก API ภายนอก "นอก" transaction ไม่ถือ lock ฐานข้อมูลระหว่างรอ
    try:
        with slip.image.open('rb') as fh:
            image_bytes = fh.read()
        filename = slip.image.name.rsplit('/', 1)[-1]
        data = easyslip_client.verify(
            image_bytes, filename=filename, content_type=CONTENT_TYPES.get(filename.rsplit('.', 1)[-1], 'image/jpeg'),
            expected_amount=slip.order.total, remark=slip.order.order_number,
        )
        amount = slip_checks.check_against_order(data, expected_total=slip.order.total, trans_ref_used=_trans_ref_used)
    except easyslip_client.SlipProblem as exc:
        return _finish_rejected(slip_id, str(exc), source=ReviewSource.AUTO)
    except (easyslip_client.ProviderUnavailable, slip_checks.ShopNotConfigured) as exc:
        logger.warning('slip %s needs manual review: %s', slip_id, exc)
        return _finish_needs_review(slip_id, f'ส่งให้เจ้าของร้านตรวจ ({exc})')

    return _finish_approved(
        slip_id, trans_ref=data.trans_ref, amount=amount, sender_name=data.sender_name,
        payload=data.raw, reviewer=None, source=ReviewSource.AUTO,
    )


def _lock_processing(slip_id, allowed=(SlipStatus.PROCESSING,)) -> SlipTransaction | None:
    slip = SlipTransaction.objects.select_for_update().select_related('order').get(pk=slip_id)
    return slip if slip.status in allowed else None


def _finish_needs_review(slip_id, reason: str) -> str:
    with transaction.atomic():
        slip = _lock_processing(slip_id)
        if slip is None:
            return SlipTransaction.objects.get(pk=slip_id).status
        slip.status, slip.reason = SlipStatus.NEEDS_REVIEW, reason[:255]
        slip.save(update_fields=['status', 'reason', 'updated_at'])
        _notify_owner_review(slip.order_id)
    return SlipStatus.NEEDS_REVIEW


def _finish_rejected(slip_id, reason: str, *, source, reviewer=None, allowed=(SlipStatus.PROCESSING,)) -> str:
    with transaction.atomic():
        slip = _lock_processing(slip_id, allowed)
        if slip is None:
            return SlipTransaction.objects.get(pk=slip_id).status
        slip.status, slip.reason = SlipStatus.REJECTED, reason[:255]
        slip.review_source, slip.reviewed_by, slip.reviewed_at = source, reviewer, timezone.now()
        slip.save(update_fields=['status', 'reason', 'review_source', 'reviewed_by', 'reviewed_at', 'updated_at'])
        if slip.order.status == OrderStatus.PAYMENT_REVIEW:
            # กลับไปรอชำระ ให้ลูกค้าแนบใหม่ได้ (นับเวลาจ่ายใหม่จากตอนนี้)
            order_service.transition_order(slip.order, OrderStatus.PENDING_PAYMENT, actor=reviewer, note=f'สลิปไม่ผ่าน: {reason}')
    return SlipStatus.REJECTED


def _finish_approved(slip_id, *, trans_ref, amount, sender_name, payload, reviewer, source,
                     allowed=(SlipStatus.PROCESSING,)) -> str:
    try:
        with transaction.atomic():
            slip = _lock_processing(slip_id, allowed)
            if slip is None:
                return SlipTransaction.objects.get(pk=slip_id).status
            if slip.order.status != OrderStatus.PAYMENT_REVIEW:
                # ออเดอร์ถูกยกเลิกระหว่างตรวจ แต่ลูกค้าโอนเงินแล้ว -> ให้เจ้าของดูและโอนคืน
                slip.status, slip.reason = SlipStatus.NEEDS_REVIEW, 'ออเดอร์ถูกยกเลิกระหว่างตรวจ ตรวจสอบและโอนคืนลูกค้า'
                slip.save(update_fields=['status', 'reason', 'updated_at'])
                return SlipStatus.NEEDS_REVIEW
            slip.status, slip.reason = SlipStatus.APPROVED, ''
            slip.trans_ref = trans_ref or None
            slip.amount_read, slip.sender_name, slip.provider_payload = amount, sender_name or '', payload or {}
            slip.review_source, slip.reviewed_by, slip.reviewed_at = source, reviewer, timezone.now()
            slip.save()
            order_service.transition_order(slip.order, OrderStatus.PAID, actor=reviewer,
                                           note='EasySlip ตรวจผ่าน' if source == ReviewSource.AUTO else 'เจ้าของร้านตรวจผ่าน')
    except IntegrityError:
        # trans_ref ซ้ำกับสลิปที่อนุมัติไปแล้ว (ส่งพร้อมกัน 2 ออเดอร์)
        return _finish_rejected(slip_id, 'สลิปนี้ถูกใช้ไปแล้ว', source=source, reviewer=reviewer, allowed=allowed)
    return SlipStatus.APPROVED  # แจ้งเตือน "ชำระแล้ว" ส่งจาก transition_order


# --------------------------------------------------------------------------- เจ้าของตรวจเอง
REVIEWABLE = (SlipStatus.NEEDS_REVIEW, SlipStatus.PROCESSING)


def approve_manually(slip: SlipTransaction, reviewer, *, trans_ref: str = '') -> str:
    trans_ref = trans_ref.strip()[:64]
    if trans_ref and _trans_ref_used(trans_ref):
        raise SlipError('รหัสธุรกรรมนี้ถูกใช้กับออเดอร์อื่นแล้ว')
    result = _finish_approved(
        slip.pk, trans_ref=trans_ref or None, amount=slip.order.total, sender_name='', payload={},
        reviewer=reviewer, source=ReviewSource.MANUAL, allowed=REVIEWABLE,
    )
    if result != SlipStatus.APPROVED:
        raise SlipError('อนุมัติไม่ได้ (สลิปถูกตรวจไปแล้ว หรือออเดอร์ถูกยกเลิก)')
    return result


def reject_manually(slip: SlipTransaction, reviewer, *, reason: str) -> str:
    reason = (reason or '').strip()
    if not reason:
        raise SlipError('กรุณาระบุเหตุผล (ลูกค้าจะเห็นข้อความนี้)')
    result = _finish_rejected(slip.pk, reason, source=ReviewSource.MANUAL, reviewer=reviewer, allowed=REVIEWABLE)
    if result != SlipStatus.REJECTED:
        raise SlipError('สลิปนี้ถูกตรวจไปแล้ว')
    return result


# --------------------------------------------------------------------------- หมดเวลาจ่าย
def payment_deadline(order: Order):
    # นับจากการเปลี่ยนสถานะล่าสุด (สั่ง หรือ สลิปไม่ผ่าน) ลูกค้าได้เวลาเต็มทุกรอบ
    return order.updated_at + timedelta(minutes=settings.PAYMENT_WINDOW_MINUTES)


def expire_unpaid_orders(now=None, batch: int = 200) -> int:
    cutoff = (now or timezone.now()) - timedelta(minutes=settings.PAYMENT_WINDOW_MINUTES)
    candidates = list(
        Order.objects.filter(status=OrderStatus.PENDING_PAYMENT, updated_at__lt=cutoff).values_list('pk', flat=True)[:batch]
    )
    expired = 0
    for order in Order.objects.filter(pk__in=candidates):
        try:
            order_service.transition_order(order, OrderStatus.CANCELLED, note='ไม่ได้ชำระเงินภายในเวลาที่กำหนด')
            expired += 1
        except order_service.InvalidTransition:
            continue  # ระหว่างนั้นลูกค้าแนบสลิปพอดี
    return expired
