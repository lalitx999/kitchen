"""
สร้างออเดอร์ และเปลี่ยนสถานะ (ที่เดียวในระบบ — CLAUDE.md กฎข้อ 2)
"""
import secrets
from dataclasses import dataclass

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import CustomerAddress
from apps.catalog.selectors import menu_selector

from ..models import Order, OrderItem, OrderStatus, OrderStatusLog
from . import pricing_service
from .cart_service import PricedCart

S = OrderStatus

# จากสถานะไหน ไปสถานะไหนได้บ้าง (นอกเหนือจากนี้ถือว่าผิด)
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    S.PENDING_PAYMENT: {S.PAYMENT_REVIEW, S.PAID, S.CANCELLED},
    S.PAYMENT_REVIEW: {S.PAID, S.PENDING_PAYMENT, S.CANCELLED},   # สลิปไม่ผ่าน -> กลับไปรอจ่าย
    S.PAID: {S.PREPARING, S.CANCELLED},
    S.PREPARING: {S.READY, S.CANCELLED},
    S.READY: {S.DELIVERING, S.CANCELLED},
    S.DELIVERING: {S.COMPLETED},
    S.COMPLETED: set(),
    S.CANCELLED: set(),
}

MAX_SAVED_ADDRESSES = 5
_ORDER_CODE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # ตัด 0/O, 1/I ที่อ่านสับสน


class OrderError(Exception):
    """ข้อความแสดงให้ลูกค้า/พนักงานเห็นได้"""


class InvalidTransition(OrderError):
    pass


@dataclass(frozen=True)
class DeliveryDetails:
    recipient_name: str
    recipient_phone: str
    address_text: str
    address_note: str
    latitude: float
    longitude: float
    note: str = ''


def _new_order_number() -> str:
    today = timezone.localdate().strftime('%y%m%d')
    code = ''.join(secrets.choice(_ORDER_CODE_ALPHABET) for _ in range(4))
    return f'TM{today}-{code}'


def _remember_address(customer, details: DeliveryDetails, point) -> None:
    existing = customer.addresses.filter(address_text=details.address_text).first()
    if existing:
        existing.location, existing.note = point, details.address_note
        existing.save(update_fields=['location', 'note', 'last_used_at', 'updated_at'])
        return
    CustomerAddress.objects.create(
        user=customer, address_text=details.address_text, note=details.address_note, location=point,
    )
    stale = list(customer.addresses.order_by('-last_used_at').values_list('pk', flat=True)[MAX_SAVED_ADDRESSES:])
    if stale:
        CustomerAddress.objects.filter(pk__in=stale).delete()


def place_order(*, customer, branch, cart: PricedCart, details: DeliveryDetails) -> Order:
    status = menu_selector.shop_status(branch)
    if not status.accepting:
        raise OrderError(status.reason)
    if cart.is_empty:
        raise OrderError('ตะกร้ายังว่าง')
    if cart.has_unavailable:
        raise OrderError('มีเมนูที่หมดแล้วในตะกร้า กรุณาลบออกก่อน')
    if not details.recipient_phone:
        raise OrderError('กรุณาใส่เบอร์โทรผู้รับ')

    try:
        point = pricing_service.make_point(details.latitude, details.longitude)
    except pricing_service.InvalidLocation as exc:
        raise OrderError(str(exc)) from exc
    quote = pricing_service.quote_delivery(branch, point)
    if not quote.within_range:
        raise OrderError(f'ที่อยู่ไกลเกินระยะส่ง ({quote.distance_km} กม.)')

    subtotal = cart.subtotal
    for _attempt in range(5):
        try:
            with transaction.atomic():
                order = Order.objects.create(
                    order_number=_new_order_number(), customer=customer, branch=branch,
                    subtotal=subtotal, delivery_fee=quote.fee, total=subtotal + quote.fee,
                    rider_fee=quote.rider_fee, distance_km=quote.distance_km,
                    recipient_name=details.recipient_name.strip(), recipient_phone=details.recipient_phone,
                    address_text=details.address_text.strip(), address_note=details.address_note.strip(),
                    delivery_location=point, note=details.note.strip(),
                )
                OrderItem.objects.bulk_create([
                    OrderItem(
                        order=order, menu_item=line.item, name=line.item.name, unit_price=line.unit_price,
                        options=[{'name': o.name, 'extra_price': str(o.extra_price)} for o in line.options],
                        quantity=line.qty, line_total=line.line_total, note=line.note,
                    )
                    for line in cart.lines
                ])
                OrderStatusLog.objects.create(order=order, to_status=S.PENDING_PAYMENT, actor=customer)
                _remember_address(customer, details, point)
            return order
        except IntegrityError:
            continue  # เลขออเดอร์ชนกัน (โอกาสน้อยมาก) สุ่มใหม่
    raise OrderError('สร้างออเดอร์ไม่สำเร็จ ลองใหม่อีกครั้ง')


def transition_order(order: Order, to_status: str, *, actor=None, note: str = '') -> Order:
    with transaction.atomic():
        # lock แถวกันสองคนกดพร้อมกัน (เช่น ครัวกดรับ ขณะลูกค้ากดยกเลิก)
        locked = Order.objects.select_for_update().get(pk=order.pk)
        if to_status not in ALLOWED_TRANSITIONS.get(locked.status, set()):
            raise InvalidTransition(
                f'เปลี่ยนจาก "{locked.get_status_display()}" เป็น "{S(to_status).label}" ไม่ได้'
            )
        now = timezone.now()
        update_fields = ['status', 'updated_at']
        from_status = locked.status
        locked.status = to_status
        if to_status == S.PAID:
            locked.paid_at = now
            update_fields.append('paid_at')
        elif to_status == S.DELIVERING:
            locked.picked_up_at = now
            update_fields.append('picked_up_at')
        elif to_status == S.COMPLETED:
            locked.completed_at = now
            update_fields.append('completed_at')
        elif to_status == S.CANCELLED:
            locked.cancelled_at = now
            locked.cancelled_reason = note[:255]
            update_fields += ['cancelled_at', 'cancelled_reason']
        locked.save(update_fields=update_fields)
        OrderStatusLog.objects.create(order=locked, from_status=from_status, to_status=to_status, actor=actor, note=note[:255])
        # แจ้งเตือนหลัง commit เท่านั้น (rollback แล้วต้องไม่มีแจ้งเตือนหลุด) · import ในฟังก์ชันกัน import วน
        from apps.notifications.services import order_events
        order_id = locked.pk
        transaction.on_commit(lambda: order_events.status_changed(order_id, from_status, to_status, note))
    return locked


def cancel_by_customer(order: Order, customer) -> Order:
    if order.customer_id != customer.pk:
        raise OrderError('ไม่พบออเดอร์')
    if not order.can_customer_cancel:
        raise OrderError('ออเดอร์นี้ยกเลิกเองไม่ได้แล้ว กรุณาโทรหาร้าน')
    return transition_order(order, S.CANCELLED, actor=customer, note='ลูกค้ายกเลิกเอง')


def cancel_by_staff(order: Order, actor, reason: str) -> Order:
    reason = (reason or '').strip()
    if not reason:
        raise OrderError('กรุณาระบุเหตุผลที่ยกเลิก')
    return transition_order(order, S.CANCELLED, actor=actor, note=reason)


# --------------------------------------------------------------------------- ไรเดอร์รับงาน / คืนงาน
# รับงานได้ตั้งแต่จ่ายเงินแล้ว (ไรเดอร์ออกไปรอที่ร้านระหว่างครัวทำได้) จนถึงอาหารพร้อม
ASSIGNABLE_STATUSES = (S.PAID, S.PREPARING, S.READY)


class AssignmentError(OrderError):
    pass


def assign_rider(order: Order, rider) -> Order:
    with transaction.atomic():
        # lock แถว: ถ้ามีไรเดอร์ 2 คนกดรับพร้อมกัน คนที่สองจะเห็นว่ามีคนรับแล้ว
        locked = Order.objects.select_for_update().get(pk=order.pk)
        if locked.status not in ASSIGNABLE_STATUSES:
            raise AssignmentError('งานนี้รับไม่ได้แล้ว')
        if locked.rider_id and locked.rider_id != rider.pk:
            raise AssignmentError('มีไรเดอร์รับงานนี้ไปแล้ว')
        if locked.rider_id == rider.pk:
            return locked
        locked.rider, locked.rider_assigned_at = rider, timezone.now()
        locked.save(update_fields=['rider', 'rider_assigned_at', 'updated_at'])
        OrderStatusLog.objects.create(order=locked, from_status=locked.status, to_status=locked.status,
                                      actor=rider, note=f'ไรเดอร์ {rider.full_name} รับงาน')
    return locked


def unassign_rider(order: Order, rider, *, note: str = 'ไรเดอร์คืนงาน') -> Order:
    with transaction.atomic():
        locked = Order.objects.select_for_update().get(pk=order.pk)
        if locked.rider_id != rider.pk:
            raise AssignmentError('ไม่ใช่งานของคุณ')
        if locked.status not in ASSIGNABLE_STATUSES:
            raise AssignmentError('รับอาหารไปแล้ว คืนงานไม่ได้')
        locked.rider, locked.rider_assigned_at = None, None
        locked.save(update_fields=['rider', 'rider_assigned_at', 'updated_at'])
        OrderStatusLog.objects.create(order=locked, from_status=locked.status, to_status=locked.status,
                                      actor=rider, note=note)
    return locked
