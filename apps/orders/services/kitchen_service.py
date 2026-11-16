"""ปุ่มบนจอครัว: รับออเดอร์ -> อาหารพร้อม / ยกเลิก (ทุกอย่างผ่าน transition_order ที่เดียว)"""
from ..models import Order, OrderStatus
from . import order_service

# ปุ่ม -> (สถานะปลายทาง, ข้อความในประวัติ)
ACTIONS = {
    'accept': (OrderStatus.PREPARING, 'ครัวรับออเดอร์'),
    'ready': (OrderStatus.READY, 'อาหารพร้อมส่ง'),
}


class KitchenError(Exception):
    """ข้อความแสดงบนจอครัวได้"""


def apply_action(order: Order, action: str, *, actor) -> Order:
    if action not in ACTIONS:
        raise KitchenError('คำสั่งไม่ถูกต้อง')
    to_status, note = ACTIONS[action]
    # แจ้งเตือนลูกค้า/ไรเดอร์ส่งจาก transition_order (notifications.order_events)
    try:
        return order_service.transition_order(order, to_status, actor=actor, note=note)
    except order_service.InvalidTransition as exc:
        # มักเกิดจากกดซ้ำ หรือมีคนอื่นเปลี่ยนสถานะไปแล้ว (เช่น เจ้าของยกเลิก)
        raise KitchenError(f'{order.order_number}: {exc}') from exc


def cancel(order: Order, *, actor, reason: str) -> Order:
    try:
        return order_service.cancel_by_staff(order, actor, reason)
    except order_service.OrderError as exc:
        raise KitchenError(str(exc)) from exc
