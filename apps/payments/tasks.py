from celery import shared_task

from .services import slip_service


@shared_task(ignore_result=True)
def verify_slip_task(slip_id: str) -> str:
    # EasySlip ล่ม/ไม่มีคีย์ไม่ retry ที่นี่ ส่งให้เจ้าของตรวจทันที ลูกค้าไม่ต้องรอนาน
    return slip_service.verify_slip(slip_id)


@shared_task(ignore_result=True)
def expire_unpaid_orders() -> int:
    return slip_service.expire_unpaid_orders()
