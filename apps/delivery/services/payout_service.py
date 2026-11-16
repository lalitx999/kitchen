"""
บันทึกการจ่ายค่าส่งให้ไรเดอร์ (D3: ระบบคำนวณ เจ้าของร้านจ่ายเอง)
รวมทุกออเดอร์ที่ "ส่งสำเร็จ" และยังไม่เคยจ่าย ของไรเดอร์คนนั้น ณ ตอนกด
"""
from decimal import Decimal

from django.db import transaction
from django.db.models import Max, Min, Sum

from apps.orders.models import Order, OrderStatus

from ..models import RiderPayout


class PayoutError(Exception):
    pass


def unpaid_orders_qs(rider):
    return Order.objects.filter(rider=rider, status=OrderStatus.COMPLETED, rider_payout__isnull=True)


def record_payout(rider, *, paid_by, expected_amount: Decimal, note: str = '') -> RiderPayout:
    """
    expected_amount = ยอดที่เจ้าของเห็นบนหน้าจอตอนกด
    ถ้าระหว่างนั้นมีงานส่งสำเร็จเพิ่ม ยอดจะไม่ตรง -> ให้กดใหม่ (กันจ่ายไม่ตรงกับที่เห็น)
    """
    with transaction.atomic():
        # lock ออเดอร์ที่จะรวม กันเจ้าของกดสองแท็บพร้อมกันแล้วบันทึกซ้ำ
        orders = list(unpaid_orders_qs(rider).select_for_update().only('id', 'rider_fee', 'completed_at'))
        if not orders:
            raise PayoutError('ไม่มีค่าส่งค้างจ่าย')
        ids = [o.pk for o in orders]
        agg = Order.objects.filter(pk__in=ids).aggregate(
            total=Sum('rider_fee'), first=Min('completed_at'), last=Max('completed_at'),
        )
        if agg['total'] != expected_amount:
            raise PayoutError(f'ยอดเปลี่ยนเป็น ฿{agg["total"]} (มีงานส่งสำเร็จเพิ่ม) กรุณาตรวจแล้วกดใหม่')
        payout = RiderPayout.objects.create(
            rider=rider, amount=agg['total'], job_count=len(ids), first_job_at=agg['first'],
            last_job_at=agg['last'], note=note.strip()[:255], paid_by=paid_by,
        )
        Order.objects.filter(pk__in=ids).update(rider_payout=payout)
    return payout
