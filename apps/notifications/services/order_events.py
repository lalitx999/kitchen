"""
ใครได้แจ้งเตือนเมื่อไร (ที่เดียว ดูง่าย)

  สลิปรอตรวจ              -> เจ้าของร้าน
  ชำระแล้ว (PAID)          -> ลูกค้า · ครัว + เจ้าของ (ออเดอร์ใหม่) · ไรเดอร์ที่เปิดรับงาน (งานใหม่)
  สลิปไม่ผ่าน (กลับรอจ่าย)  -> ลูกค้า
  กำลังทำ                  -> ลูกค้า
  อาหารพร้อม               -> ไรเดอร์ที่รับงาน (ยังไม่มีคนรับ -> ไรเดอร์ที่เปิดรับงานทุกคน)
  กำลังไปส่ง                -> ลูกค้า
  ไรเดอร์ใกล้ถึง (< 500 ม.) -> ลูกค้า (ครั้งเดียวต่อออเดอร์)
  ส่งสำเร็จ                 -> ลูกค้า
  ยกเลิก                   -> ลูกค้า + ไรเดอร์ที่รับงาน

ถูกเรียกหลัง commit จาก orders/payments/delivery เท่านั้น — ล้มเหลวก็ไม่กระทบออเดอร์
"""
import logging

from django.core.cache import cache
from django.urls import reverse

from apps.accounts.models import Role, User
from apps.orders.models import Order, OrderStatus

from .notify_service import notify

logger = logging.getLogger(__name__)
S = OrderStatus


def _staff(*roles):
    return list(User.objects.filter(role__in=roles, is_active=True).only('id', 'is_active'))


def _online_riders():
    return list(User.objects.filter(role=Role.RIDER, is_active=True, rider_profile__is_online=True).only('id', 'is_active'))


def _short(order: Order) -> str:
    return order.order_number[-4:]


def status_changed(order_id, from_status: str, to_status: str, note: str = '') -> None:
    try:
        _status_changed(order_id, from_status, to_status, note)
    except Exception:  # noqa: BLE001 - แจ้งเตือนพังต้องไม่ทำให้ขั้นตอนหลักพัง
        logger.exception('notification failed for order %s %s->%s', order_id, from_status, to_status)


def _status_changed(order_id, from_status, to_status, note):
    order = Order.objects.select_related('customer', 'rider').filter(pk=order_id).first()
    if order is None:
        return
    customer_url = reverse('orders:detail', args=[order.pk])
    short = _short(order)

    if to_status == S.PAID:
        notify([order.customer], kind='order.paid', title='ชำระเงินแล้ว',
               body=f'ออเดอร์ {short} ส่งเข้าครัวแล้ว', url=customer_url)
        notify(_staff(Role.KITCHEN, Role.OWNER), kind='kitchen.new', title=f'ออเดอร์ใหม่ {short}',
               body=f'{order.recipient_name} · ฿{order.total:,.0f}', url=reverse('orders:kitchen'))
        if order.rider_id is None:
            notify(_online_riders(), kind='job.new', title='มีงานใหม่',
                   body=f'ออเดอร์ {short} · {order.distance_km} กม. · ค่าส่ง ฿{order.rider_fee:,.0f}',
                   url=reverse('delivery:rider_home'))
    elif to_status == S.PENDING_PAYMENT and from_status == S.PAYMENT_REVIEW:
        notify([order.customer], kind='slip.rejected', title='สลิปไม่ผ่าน',
               body=(note.replace('สลิปไม่ผ่าน: ', '') or 'กรุณาแนบสลิปใหม่')[:200], url=customer_url)
    elif to_status == S.PREPARING:
        notify([order.customer], kind='order.preparing', title='ครัวกำลังทำอาหาร', body=f'ออเดอร์ {short}', url=customer_url)
    elif to_status == S.READY:
        riders = [order.rider] if order.rider_id else _online_riders()
        notify(riders, kind='job.ready', title=f'อาหารพร้อม {short}', body='มารับที่ร้านได้เลย',
               url=reverse('delivery:rider_home'))
    elif to_status == S.DELIVERING:
        notify([order.customer], kind='order.delivering', title='ไรเดอร์กำลังไปส่ง',
               body=f'ออเดอร์ {short} ออกจากร้านแล้ว', url=customer_url)
    elif to_status == S.COMPLETED:
        notify([order.customer], kind='order.completed', title='ส่งสำเร็จ',
               body=f'ออเดอร์ {short} ถึงแล้ว ขอบคุณที่สั่งครับ', url=customer_url)
    elif to_status == S.CANCELLED:
        reason = note or 'ร้านยกเลิกออเดอร์'
        notify([order.customer], kind='order.cancelled', title=f'ออเดอร์ {short} ถูกยกเลิก', body=reason, url=customer_url)
        if order.rider_id:
            notify([order.rider], kind='job.cancelled', title=f'งาน {short} ถูกยกเลิก', body=reason,
                   url=reverse('delivery:rider_home'))


def slip_needs_review(order_id) -> None:
    try:
        order = Order.objects.filter(pk=order_id).only('id', 'order_number', 'total').first()
        if order:
            notify(_staff(Role.OWNER), kind='slip.review', title='มีสลิปรอตรวจ',
                   body=f'ออเดอร์ {_short(order)} · ฿{order.total:,.0f}', url=reverse('console:slips'))
    except Exception:  # noqa: BLE001
        logger.exception('slip review notification failed for %s', order_id)


def rider_near(order: Order) -> None:
    """เรียกจากการส่งพิกัด: แจ้งลูกค้าครั้งเดียวต่อออเดอร์ (cache.add สำเร็จครั้งแรกเท่านั้น)"""
    if cache.add(f'notify:near:{order.pk}', 1, 6 * 60 * 60):
        notify([order.customer], kind='order.near', title='ไรเดอร์ใกล้ถึงแล้ว',
               body='เตรียมรับอาหารได้เลย', url=reverse('orders:detail', args=[order.pk]))
