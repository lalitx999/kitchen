"""
งานของไรเดอร์
  รับงาน (จ่ายแล้ว/กำลังทำ/พร้อมส่ง) -> รับอาหารที่ร้าน [กำลังไปส่ง] -> ถ่ายรูปส่งสำเร็จ [ส่งสำเร็จ]
สถานะออเดอร์เปลี่ยนผ่าน orders.order_service เท่านั้น
"""
from django.contrib.gis.geos import Point
from django.db import transaction

from apps.core import images
from apps.orders.models import Order, OrderStatus
from apps.orders.services import order_service

from ..models import MAX_PROOF_PHOTOS, DeliveryProof, DeliveryProofPhoto
from . import live_location_service

PROOF_MAX_BYTES = 6 * 1024 * 1024   # รูปจากกล้องมือถือใหญ่กว่าสลิป


class JobError(Exception):
    """ข้อความแสดงบนหน้าไรเดอร์ได้"""


def _require_own(order: Order, rider):
    if order.rider_id != rider.pk:
        raise JobError('ไม่ใช่งานของคุณ')


def accept(order: Order, rider, *, profile) -> Order:
    if not profile.is_online:
        raise JobError('กด "เริ่มรับงาน" ก่อน')
    try:
        return order_service.assign_rider(order, rider)
    except order_service.OrderError as exc:
        raise JobError(str(exc)) from exc


def release(order: Order, rider) -> Order:
    try:
        return order_service.unassign_rider(order, rider)
    except order_service.OrderError as exc:
        raise JobError(str(exc)) from exc


def arrive_at_shop(order: Order, rider) -> Order:
    """กด "ถึงร้านแล้ว": ครัวเห็นว่ามีไรเดอร์รออยู่ (กดซ้ำได้)"""
    try:
        return order_service.mark_rider_arrived(order, rider)
    except order_service.OrderError as exc:
        raise JobError(str(exc)) from exc


def pick_up(order: Order, rider) -> Order:
    _require_own(order, rider)
    if order.status != OrderStatus.READY:
        raise JobError('ครัวยังทำอาหารไม่เสร็จ รอให้ขึ้นว่า "อาหารพร้อม" ก่อน')
    try:
        return order_service.transition_order(order, OrderStatus.DELIVERING, actor=rider, note='ไรเดอร์รับอาหารแล้ว')
    except order_service.InvalidTransition as exc:
        raise JobError(str(exc)) from exc


def complete(order: Order, rider, *, photos, latitude=None, longitude=None) -> Order:
    """ส่งสำเร็จต้องมีรูปถ่าย 1-4 รูปเสมอ (หลักฐานเมื่อลูกค้าบอกว่าไม่ได้รับของ)"""
    _require_own(order, rider)
    if order.status != OrderStatus.DELIVERING:
        raise JobError('ออเดอร์นี้ยังไม่ได้อยู่ในสถานะกำลังไปส่ง')
    photos = [p for p in (photos or []) if p]
    if not photos:
        raise JobError('ถ่ายรูปตอนส่งของอย่างน้อย 1 รูป')
    if len(photos) > MAX_PROOF_PHOTOS:
        raise JobError(f'ส่งรูปได้ไม่เกิน {MAX_PROOF_PHOTOS} รูป')
    checked = []
    for index, photo in enumerate(photos, start=1):
        try:
            _data, ext = images.read_uploaded_image(photo, max_bytes=PROOF_MAX_BYTES)
        except images.InvalidImage as exc:
            raise JobError(f'รูปที่ {index}: {exc}') from exc
        checked.append((photo, ext))

    location, distance_m = None, None
    try:
        location = Point(float(longitude), float(latitude), srid=4326)
        if location.x == 0 and location.y == 0:
            location = None
    except (TypeError, ValueError):
        location = None  # ไม่มีพิกัดก็ส่งได้ (GPS อาจไม่พร้อม) แต่ต้องมีรูป
    if location is not None:
        # ระยะจากจุดกดส่งถึงหมุดลูกค้า (เมตร) แบบประมาณ ใช้ดูย้อนหลังเท่านั้น
        distance_m = int(live_location_service.haversine_m(location.y, location.x,
                                                            order.delivery_location.y, order.delivery_location.x))

    with transaction.atomic():
        proof = DeliveryProof.objects.create(order=order, rider=rider, location=location, distance_to_customer_m=distance_m)
        for index, (photo, ext) in enumerate(checked):
            row = DeliveryProofPhoto(proof=proof, sort_order=index)
            row.photo.save(f'proof.{ext}', photo, save=False)
            row.save()
        try:
            order = order_service.transition_order(order, OrderStatus.COMPLETED, actor=rider,
                                                   note=f'ส่งสำเร็จ (มีรูปหลักฐาน {len(checked)} รูป)')
        except order_service.InvalidTransition as exc:
            raise JobError(str(exc)) from exc
    # ไม่มีงานค้างแล้ว -> ไม่ต้องแสดงตำแหน่งให้ลูกค้าเห็นต่อ (ความเป็นส่วนตัวของไรเดอร์)
    if not Order.objects.filter(rider=rider, status=OrderStatus.DELIVERING).exists():
        live_location_service.clear(rider.pk)
    return order



NEAR_METERS = 500


def check_near_customers(rider, location) -> None:
    """ไรเดอร์เข้าใกล้บ้านลูกค้า < 500 ม. -> แจ้งลูกค้า (ครั้งเดียวต่อออเดอร์ กันใน order_events)"""
    from apps.notifications.services import order_events

    for order in Order.objects.filter(rider=rider, status=OrderStatus.DELIVERING).select_related('customer'):
        meters = live_location_service.haversine_m(location.lat, location.lng,
                                                   order.delivery_location.y, order.delivery_location.x)
        if meters < NEAR_METERS:
            order_events.rider_near(order)
